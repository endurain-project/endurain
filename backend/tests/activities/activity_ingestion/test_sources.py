"""Tests for the ingestion source objects.

These replaced six loosely-related keyword arguments threaded through the
pipeline, so what is tested here is mostly *decisions the source now owns*: which
metadata applies to a file, where a failed file goes, and whether one activity of
a multi-activity file should be imported at all.
"""

from unittest.mock import patch

import core.config as core_config
import modules.activities.activity_ingestion.sources as sources


class TestSourceKinds:
    def test_each_source_names_its_provenance(self):
        assert sources.UploadSource().kind == "upload"
        assert sources.GarminSource().kind == "garmin"
        assert sources.BulkImportSource().kind == "bulk_import"


class TestIsStrava:
    def test_true_only_when_the_csv_data_is_present(self):
        assert sources.BulkImportSource(strava_activities={"f.fit": {}}).is_strava is True
        assert sources.BulkImportSource().is_strava is False
        assert sources.BulkImportSource(strava_activities={}).is_strava is False


class TestErrorDirectory:
    def test_strava_import_uses_the_strava_error_directory(self):
        source = sources.BulkImportSource(strava_activities={"f.fit": {}})
        assert source.error_directory == core_config.STRAVA_BULK_IMPORT_IMPORT_ERRORS_DIR

    def test_generic_import_uses_the_generic_error_directory(self):
        assert sources.BulkImportSource().error_directory == core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR


class TestMetadataFor:
    def test_no_metadata_without_an_initiated_time(self):
        assert sources.BulkImportSource(strava_activities={"f.fit": {}}).metadata_for("f.fit") == {}

    @patch("modules.activities.activity_ingestion.sources.strava_bulk_import_utils")
    def test_strava_import_builds_the_full_metadata_dict(self, mock_strava):
        mock_strava.build_metadata_dict.return_value = {"name": "Morning Ride"}
        source = sources.BulkImportSource(
            import_initiated_time="2026-07-21T00:00:00",
            strava_activities={"f.fit": {}},
            gear_nickname_to_id={"Bike": 3},
        )

        assert source.metadata_for("f.fit") == {"name": "Morning Ride"}
        mock_strava.build_metadata_dict.assert_called_once_with(
            "f.fit", {"f.fit": {}}, "2026-07-21T00:00:00", {"Bike": 3}
        )

    @patch("modules.activities.activity_ingestion.sources.strava_bulk_import_utils")
    def test_generic_import_records_only_the_import(self, mock_strava):
        mock_strava.build_import_dictionary.return_value = {"import_ISO_time": "2026-07-21T00:00:00"}
        source = sources.BulkImportSource(import_initiated_time="2026-07-21T00:00:00")

        assert source.metadata_for("f.gpx") == {"import_dict": {"import_ISO_time": "2026-07-21T00:00:00"}}
        mock_strava.build_import_dictionary.assert_called_once_with("f.gpx", "2026-07-21T00:00:00", False)


class TestShouldImport:
    """Strava lists a multi-activity .fit once per activity it contains."""

    def test_single_activity_file_is_always_imported(self):
        source = sources.BulkImportSource(strava_activities={"f.fit": {}})
        assert source.should_import("activity", {"metadata_found_in_csv": True}, activities_in_file=1) is True

    def test_generic_import_never_skips(self):
        assert sources.BulkImportSource().should_import("activity", {}, activities_in_file=5) is True

    def test_imports_when_the_csv_has_no_row_for_the_file(self):
        source = sources.BulkImportSource(strava_activities={"f.fit": {}})
        assert source.should_import("activity", {"metadata_found_in_csv": False}, activities_in_file=5) is True

    @patch("modules.activities.activity_ingestion.sources.strava_bulk_import_utils")
    def test_imports_the_activity_whose_start_time_matches_the_csv(self, mock_strava):
        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = True
        source = sources.BulkImportSource(strava_activities={"f.fit": {}})

        assert source.should_import("activity", {"metadata_found_in_csv": True}, activities_in_file=5) is True

    @patch("modules.activities.activity_ingestion.sources.strava_bulk_import_utils")
    def test_skips_the_activities_the_csv_row_does_not_refer_to(self, mock_strava):
        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = False
        source = sources.BulkImportSource(strava_activities={"f.fit": {}})

        assert source.should_import("activity", {"metadata_found_in_csv": True}, activities_in_file=5) is False
        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.assert_called_once()
