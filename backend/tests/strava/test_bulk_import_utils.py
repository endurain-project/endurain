"""Tests for Strava bulk-import file handling."""

from __future__ import annotations

from unittest.mock import Mock

from fastapi import HTTPException

import modules.activities.activity.contracts as activities_contracts
import modules.strava.bulk_import_utils as bulk_import_utils
from core.file_uploads import UploadKind


def _activity(start_time: str) -> activities_contracts.ActivityCore:
    """An ActivityCore as the FIT parser produces it (start_time coerced to aware UTC)."""
    return activities_contracts.ActivityCore(
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


def test_bulk_media_import_validates_before_storing(tmp_path, monkeypatch):
    """Media import validates images before handing the bytes to the media module."""
    validate = Mock()
    store_media = Mock()

    strava_dir = tmp_path / "strava"
    strava_dir.mkdir()
    photo = strava_dir / "photo.jpg"
    photo.write_bytes(b"image-bytes")

    monkeypatch.setattr(
        bulk_import_utils.core_config,
        "STRAVA_BULK_IMPORT_MEDIA_DIR",
        str(strava_dir),
        raising=False,
    )
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file_sync", validate)
    monkeypatch.setattr(
        bulk_import_utils.activity_media_integration,
        "attach_media_bytes",
        store_media,
    )

    bulk_import_utils.create_activity_media_from_strava_bulk_import(7, "photo.jpg", str(photo), Mock())

    validate.assert_called_once_with(
        str(photo),
        kind=UploadKind.IMAGE,
        filename="photo.jpg",
    )
    # The media module owns the key and the storage area; only bytes cross over.
    assert store_media.call_args.args[0] == 7
    assert store_media.call_args.args[1] == "photo.jpg"
    assert store_media.call_args.args[2] == b"image-bytes"
    # The staged Strava copy is consumed.
    assert not photo.exists()


def test_bulk_media_import_rejects_invalid_image(tmp_path, monkeypatch):
    """Invalid media is rejected before it is stored or recorded."""
    validate = Mock(side_effect=HTTPException(status_code=400, detail="bad image"))
    store_media = Mock()

    strava_dir = tmp_path / "strava"
    strava_dir.mkdir()
    photo = strava_dir / "photo.jpg"
    photo.write_bytes(b"not an image")

    monkeypatch.setattr(
        bulk_import_utils.core_config,
        "STRAVA_BULK_IMPORT_MEDIA_DIR",
        str(strava_dir),
        raising=False,
    )
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file_sync", validate)
    monkeypatch.setattr(
        bulk_import_utils.activity_media_integration,
        "attach_media_bytes",
        store_media,
    )

    bulk_import_utils.create_activity_media_from_strava_bulk_import(7, "photo.jpg", str(photo), Mock())

    validate.assert_called_once()
    store_media.assert_not_called()
    assert photo.exists()


def test_bulk_media_import_skips_a_missing_file(tmp_path, monkeypatch):
    """A media entry with no file on disk is skipped without storing anything."""
    store_media = Mock()
    monkeypatch.setattr(
        bulk_import_utils.activity_media_integration,
        "attach_media_bytes",
        store_media,
    )

    bulk_import_utils.create_activity_media_from_strava_bulk_import(7, "photo.jpg", str(tmp_path / "gone.jpg"), Mock())

    store_media.assert_not_called()


def test_activity_scan_skips_a_symlink_out_of_the_import_directory(tmp_path, monkeypatch):
    """Following it would import an arbitrary file from the server's disk."""
    validate = Mock()
    activities_dir = tmp_path / "strava_import" / "activities"
    activities_dir.mkdir(parents=True)
    (tmp_path / "media").mkdir()
    outside = tmp_path / "secrets.gpx"
    outside.write_bytes(b"<gpx/>")
    (activities_dir / "ride.gpx").symlink_to(outside)

    monkeypatch.setattr(
        bulk_import_utils.core_config, "STRAVA_BULK_IMPORT_ACTIVITIES_DIR", str(activities_dir), raising=False
    )
    monkeypatch.setattr(
        bulk_import_utils.core_config, "STRAVA_BULK_IMPORT_MEDIA_DIR", str(tmp_path / "media"), raising=False
    )
    monkeypatch.setattr(bulk_import_utils.file_uploads, "validate_local_file", validate)

    queued = bulk_import_utils.queue_bulk_export_activities_for_import(7, Mock(), Mock(), {}, {}, "2026-08-21T00:00:00")

    assert queued == 0
    # Rejected before anything opens it.
    validate.assert_not_called()


def test_gear_dictionary_normal(monkeypatch):
    """Smoosh key is built correctly with clean values."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=1, brand="Nike", model="Pegasus", nickname="Fast Shoes"),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert result["Fast Shoes"] == [1]
    assert result["Nike Pegasus Fast Shoes"] == [1]


def test_gear_dictionary_trailing_whitespace(monkeypatch):
    """Smoosh key strips trailing whitespace from brand/model/nickname."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=2, brand="Nike ", model=" Pegasus ", nickname="Fast Shoes "),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert "Nike  Pegasus  Fast Shoes " not in result
    assert result["Nike Pegasus Fast Shoes"] == [2]


def test_gear_dictionary_none_fields(monkeypatch):
    """Smoosh key handles None brand/model without TypeError."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=3, brand=None, model=None, nickname="Unbranded"),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert result["Unbranded"] == [3]


def test_gear_dictionary_leading_whitespace(monkeypatch):
    """Smoosh key strips leading whitespace from brand/model/nickname."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    gear_items = [
        _MockGear(gear_id=4, brand=" Nike", model=" Pegasus", nickname=" Pegasus"),
    ]
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: gear_items)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is not None
    assert result["Nike Pegasus Pegasus"] == [4]


def test_gear_dictionary_no_user(monkeypatch):
    """Returns None when user does not exist."""
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: None)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is None


def test_gear_dictionary_no_gear(monkeypatch):
    """Returns None when user has no gear."""
    mock_user = Mock(id=42)
    monkeypatch.setattr(bulk_import_utils.users_crud, "get_user_by_id", lambda uid, db: mock_user)
    monkeypatch.setattr(bulk_import_utils.gears_crud, "get_gear_user", lambda uid, db: None)

    result = bulk_import_utils.create_gear_dictionary_for_bulk_import(42, Mock())

    assert result is None
