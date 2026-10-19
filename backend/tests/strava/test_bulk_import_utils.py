"""Tests for Strava bulk-import file handling."""

from __future__ import annotations

from unittest.mock import Mock

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.strava.bulk_import_utils as bulk_import_utils
from core.file_uploads import UploadKind


def _activity(start_time: str) -> activity_contracts.ActivityCore:
    """An ActivityCore as the FIT parser produces it (start_time coerced to aware UTC)."""
    return activity_contracts.ActivityCore(
        user_id=1,
        name="Workout",
        distance=1000,
        activity_type=1,
        start_time=start_time,
        end_time="2023-10-21T08:41:47",
    )


class TestDoesActivityStartTimeMatchTheCsv:
    """Selects which activity of a multi-activity .fit a Strava CSV row refers to."""

    def test_matching_start_times_are_recognised(self):
        # Regression: ActivityCore coerces start_time to an aware datetime at
        # construction, but this comparison parsed it as an ISO *string*. That
        # raised TypeError for every multi-activity .fit in a Strava export,
        # which the bulk entry caught and turned into "move the whole file to
        # the import-error directory" — so none of its activities imported.
        assert (
            bulk_import_utils.does_activity_start_time_match_the_data_in_strava_activities_csv(
                _activity("2023-10-21T07:41:47"),
                {"activity date": "Oct 21, 2023, 7:41:47 AM"},
            )
            is True
        )

    def test_differing_start_times_are_rejected(self):
        assert (
            bulk_import_utils.does_activity_start_time_match_the_data_in_strava_activities_csv(
                _activity("2023-10-21T07:41:47"),
                {"activity date": "Oct 21, 2023, 8:13:28 AM"},
            )
            is False
        )


class _MockGear:
    def __init__(self, gear_id: int, brand: str | None, model: str | None, nickname: str):
        self.id = gear_id
        self.brand = brand
        self.model = model
        self.nickname = nickname


def test_media_is_validated_as_an_image_before_it_is_stored(monkeypatch):
    """The bytes are checked through the upload pipeline before the media module sees them."""
    validate = Mock()
    store_media = Mock()
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file_sync", validate)
    monkeypatch.setattr(bulk_import_utils.activity_media_integration, "attach_media_bytes", store_media)

    bulk_import_utils.create_activity_media_from_strava_bulk_import(7, "photo.jpg", b"image-bytes", Mock())

    assert validate.call_args.kwargs == {"kind": UploadKind.IMAGE, "filename": "photo.jpg"}
    # The media module owns the key and the storage area; only bytes cross over.
    assert store_media.call_args.args[:3] == (7, "photo.jpg", b"image-bytes")


def test_invalid_media_is_rejected_before_it_is_stored(monkeypatch):
    validate = Mock(side_effect=core_exceptions.InvalidInputError("bad image"))
    store_media = Mock()
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file_sync", validate)
    monkeypatch.setattr(bulk_import_utils.activity_media_integration, "attach_media_bytes", store_media)

    bulk_import_utils.create_activity_media_from_strava_bulk_import(7, "photo.jpg", b"not an image", Mock())

    store_media.assert_not_called()


class TestMediaFromTheArchive:
    def _activity(self):
        return Mock(id=11)

    def test_each_listed_photo_is_read_from_the_exports_media_folder(self, monkeypatch):
        store = Mock()
        monkeypatch.setattr(bulk_import_utils, "create_activity_media_from_strava_bulk_import", store)
        read = Mock(side_effect=lambda name: {"media/a.jpg": b"A", "media/b.jpg": b"B"}.get(name))
        rows = {"ride.fit": {"Media": "media/a.jpg|media/b.jpg"}}

        bulk_import_utils.import_media_from_strava_bulk_export(rows, self._activity(), "ride.fit", read, Mock())

        assert [call.args[1:3] for call in store.call_args_list] == [("a.jpg", b"A"), ("b.jpg", b"B")]

    def test_a_photo_missing_from_the_export_is_skipped_not_fatal(self, monkeypatch):
        store = Mock()
        monkeypatch.setattr(bulk_import_utils, "create_activity_media_from_strava_bulk_import", store)
        read = Mock(side_effect=lambda name: b"B" if name == "media/b.jpg" else None)
        rows = {"ride.fit": {"Media": "media/a.jpg|media/b.jpg"}}

        bulk_import_utils.import_media_from_strava_bulk_export(rows, self._activity(), "ride.fit", read, Mock())

        assert store.call_count == 1

    def test_a_row_without_media_reads_nothing(self, monkeypatch):
        read = Mock()
        rows = {"ride.fit": {"Media": "  "}}

        bulk_import_utils.import_media_from_strava_bulk_export(rows, self._activity(), "ride.fit", read, Mock())

        read.assert_not_called()

    def test_a_path_in_the_manifest_cannot_reach_outside_the_media_folder(self, monkeypatch):
        """Only the base name is used, so a crafted entry cannot name another member."""
        read = Mock(return_value=None)
        rows = {"ride.fit": {"Media": "../activities/secret.fit"}}

        bulk_import_utils.import_media_from_strava_bulk_export(rows, self._activity(), "ride.fit", read, Mock())

        read.assert_called_once_with("media/secret.fit")


class TestParseActivitiesManifest:
    HEADER = "Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,Elapsed Time,Filename,Activity Gear,Media\n"

    def _write(self, tmp_path, body: str) -> str:
        path = tmp_path / "activities.csv"
        path.write_text(body)
        return str(path)

    def test_rows_are_keyed_by_the_files_base_name(self, tmp_path):
        path = self._write(
            tmp_path, self.HEADER + '1,"Oct 21, 2023, 7:41:47 AM",Ride,Ride,,10,activities/123.fit.gz,Bike,\n'
        )

        parsed = bulk_import_utils.parse_activities_manifest(path)

        assert list(parsed) == ["123.fit.gz"]
        assert parsed["123.fit.gz"]["Activity Name"] == "Ride"

    def test_a_manifest_without_the_required_headers_is_refused(self, tmp_path):
        path = self._write(tmp_path, "Activity ID,Filename\n1,activities/1.fit\n")

        assert bulk_import_utils.parse_activities_manifest(path) is None

    def test_an_unreadable_manifest_is_refused_not_raised(self, tmp_path):
        assert bulk_import_utils.parse_activities_manifest(str(tmp_path / "missing.csv")) is None


def _gear(monkeypatch, items):
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: items)


def test_gear_dictionary_normal(monkeypatch):
    """Smoosh key is built correctly with clean values."""
    _gear(monkeypatch, [_MockGear(gear_id=1, brand="Nike", model="Pegasus", nickname="Fast Shoes")])

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result["Fast Shoes"] == [1]
    assert result["Nike Pegasus Fast Shoes"] == [1]


def test_gear_dictionary_strips_surrounding_whitespace(monkeypatch):
    _gear(monkeypatch, [_MockGear(gear_id=2, brand="Nike ", model=" Pegasus ", nickname="Fast Shoes ")])

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result["Nike Pegasus Fast Shoes"] == [2]


def test_gear_dictionary_handles_missing_brand_and_model(monkeypatch):
    _gear(monkeypatch, [_MockGear(gear_id=3, brand=None, model=None, nickname="Unbranded")])

    assert bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())["Unbranded"] == [3]


def test_a_user_with_no_gear_gets_an_empty_map_not_an_aborted_import(monkeypatch):
    """No gear only means no activity is linked to one; the import still runs."""
    _gear(monkeypatch, None)

    assert bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock()) == {}
