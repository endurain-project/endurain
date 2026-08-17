"""Tests for the Strava-export bulk-import source.

These behaviours used to live on ``BulkImportSource`` in the activities module,
which meant activities imported Strava while Strava imported the ingestion entry
point. They are asserted here, against the subclass, because that is where the
knowledge belongs.
"""

from unittest.mock import patch

import core.config as core_config
import modules.activities.activity.contracts as activities_contracts
import modules.strava.bulk_import_source as strava_bulk_import_source


def _activity() -> activities_contracts.ActivityCore:
    return activities_contracts.ActivityCore(
        user_id=1,
        name="Workout",
        distance=1000,
        activity_type=1,
        start_time="2023-10-21T07:41:47",
        end_time="2023-10-21T08:41:47",
    )


def _source(**kwargs) -> strava_bulk_import_source.StravaBulkImportSource:
    return strava_bulk_import_source.StravaBulkImportSource(**kwargs)


class TestSourceKind:
    def test_it_is_still_a_bulk_import(self):
        # The pipeline narrows on the base type, so the subclass must satisfy it.
        assert _source().kind == "bulk_import"
        assert isinstance(_source(), strava_bulk_import_source.ingestion_sources.BulkImportSource)


class TestErrorDirectory:
    def test_failures_land_in_the_shared_strava_directory(self):
        assert _source().error_directory == core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR


class TestMetadataFor:
    def test_no_metadata_without_an_initiated_time(self):
        assert _source(strava_activities={"f.fit": {}}).metadata_for("f.fit") == {}

    @patch("modules.strava.bulk_import_source.strava_bulk_import_utils")
    def test_builds_the_full_metadata_dict_from_the_csv(self, mock_utils):
        mock_utils.build_metadata_dict.return_value = {"name": "Morning Ride"}
        source = _source(
            import_initiated_time="2026-07-21T00:00:00",
            strava_activities={"f.fit": {}},
            gear_nickname_to_id={"Bike": 3},
        )

        assert source.metadata_for("f.fit") == {"name": "Morning Ride"}
        mock_utils.build_metadata_dict.assert_called_once_with(
            "f.fit", {"f.fit": {}}, "2026-07-21T00:00:00", {"Bike": 3}
        )

    def test_falls_back_to_the_plain_import_record_without_a_csv(self):
        source = _source(import_initiated_time="2026-07-21T00:00:00")

        assert source.metadata_for("f.gpx")["import_dict"]["import_source"] == "Basic bulk import"


class TestShouldImport:
    """Strava lists a multi-activity .fit once per activity it contains."""

    def test_single_activity_file_is_always_imported(self):
        source = _source(strava_activities={"f.fit": {}})
        assert source.should_import("activity", {"metadata_found_in_csv": True}, activities_in_file=1) is True

    def test_imports_when_the_csv_has_no_row_for_the_file(self):
        source = _source(strava_activities={"f.fit": {}})
        assert source.should_import("activity", {"metadata_found_in_csv": False}, activities_in_file=5) is True

    @patch("modules.strava.bulk_import_source.strava_bulk_import_utils")
    def test_imports_the_activity_whose_start_time_matches_the_csv(self, mock_utils):
        mock_utils.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = True
        source = _source(strava_activities={"f.fit": {}})

        assert source.should_import("activity", {"metadata_found_in_csv": True}, activities_in_file=5) is True

    @patch("modules.strava.bulk_import_source.strava_bulk_import_utils")
    def test_skips_the_activities_the_csv_row_does_not_refer_to(self, mock_utils):
        mock_utils.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = False
        source = _source(strava_activities={"f.fit": {}})

        assert source.should_import("activity", {"metadata_found_in_csv": True}, activities_in_file=5) is False
        mock_utils.does_activity_start_time_match_the_data_in_strava_activities_csv.assert_called_once()


class TestApplyMetadata:
    def test_it_reuses_the_shared_applier(self):
        activity = _activity()

        _source().apply_metadata(activity, {"name": "Morning Ride", "gear_id": 4})

        assert (activity.name, activity.gear_id) == ("Morning Ride", 4)


class TestImportSideArtifacts:
    @patch("modules.strava.bulk_import_source.strava_bulk_import_utils")
    def test_attaches_the_sidecar_photos_to_the_last_created_activity(self, mock_utils):
        created = ["first", "last"]
        source = _source(strava_activities={"f.fit": {}})

        source.import_side_artifacts(created, "f.fit", "db")

        mock_utils.import_media_from_strava_bulk_export.assert_called_once_with({"f.fit": {}}, "last", "f.fit", "db")

    @patch("modules.strava.bulk_import_source.strava_bulk_import_utils")
    def test_nothing_to_attach_without_created_activities(self, mock_utils):
        _source(strava_activities={"f.fit": {}}).import_side_artifacts([], "f.fit", "db")

        mock_utils.import_media_from_strava_bulk_export.assert_not_called()
