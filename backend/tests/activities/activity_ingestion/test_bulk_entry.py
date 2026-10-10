"""Tests for the background ingestion entry points.

The two entries share a pipeline and differ only in their failure contract:
``store_bulk_import_file`` raises (a durable job body, so the runner can retry),
``store_activity_file`` swallows and quarantines the file (so a batch continues).
"""

from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity_ingestion.bulk_entry as bulk_entry
import modules.activities.activity_ingestion.sources as sources


class TestStoreBulkImportFile:
    """The raising per-file body for the durable bulk-import job."""

    def test_delegates_to_the_pipeline_as_a_bulk_import(self):
        with patch.object(bulk_entry.pipeline, "validate_prepare_and_store_file", return_value=["activity"]) as helper:
            result = bulk_entry.store_bulk_import_file(3, "/tmp/x.gpx", "2026-07-21T00:00:00", "db")

        assert result == ["activity"]
        assert helper.call_args.args == (3, "/tmp/x.gpx", "db")
        assert helper.call_args.kwargs["source"] == sources.BulkImportSource(
            import_initiated_time="2026-07-21T00:00:00", user_id=3
        )

    def test_propagates_failure_instead_of_swallowing(self):
        with (
            patch.object(bulk_entry.pipeline, "validate_prepare_and_store_file", side_effect=ValueError("boom")),
            pytest.raises(ValueError),
        ):
            bulk_entry.store_bulk_import_file(3, "/tmp/x.gpx", "2026-07-21T00:00:00", "db")


class TestStoreActivityFile:
    """The swallowing entry used by the Garmin sync and the Strava bulk import."""

    def test_returns_the_created_activities(self):
        with patch.object(bulk_entry.pipeline, "validate_prepare_and_store_file", return_value=["activity"]):
            result = bulk_entry.store_activity_file(3, "/tmp/x.gpx", "db", source=sources.GarminSource())

        assert result == ["activity"]

    def test_returns_none_on_failure(self):
        with patch.object(bulk_entry.pipeline, "validate_prepare_and_store_file", side_effect=ValueError("boom")):
            result = bulk_entry.store_activity_file(3, "/tmp/x.gpx", "db", source=sources.GarminSource())

        assert result is None

    def test_a_failed_garmin_file_is_not_quarantined(self):
        # Only bulk imports have an error directory; the Garmin sync cleans up
        # its own extracted file instead.
        with (
            patch.object(bulk_entry.pipeline, "validate_prepare_and_store_file", side_effect=ValueError("boom")),
            patch.object(bulk_entry, "_move_failed_file_to_error_directory") as move,
        ):
            bulk_entry.store_activity_file(3, "/tmp/x.gpx", "db", source=sources.GarminSource())

        move.assert_not_called()

    def test_a_failed_bulk_import_file_is_quarantined(self):
        source = sources.BulkImportSource(import_initiated_time="2026-07-21T00:00:00")

        with (
            patch.object(bulk_entry.pipeline, "validate_prepare_and_store_file", side_effect=ValueError("boom")),
            patch.object(bulk_entry, "_move_failed_file_to_error_directory") as move,
        ):
            bulk_entry.store_activity_file(3, "/tmp/x.gpx", "db", source=source)

        move.assert_called_once_with(source, "/tmp/x.gpx")


class TestMoveFailedFileToErrorDirectory:
    def test_moves_the_file_into_the_sources_error_directory(self, tmp_path):
        source = sources.BulkImportSource()

        with (
            patch.object(bulk_entry.core_file_uploads, "move_within") as move,
            patch.object(bulk_entry.os, "makedirs"),
        ):
            bulk_entry._move_failed_file_to_error_directory(source, "/tmp/bad.gpx")

        assert move.call_args.args[0] == "/tmp/bad.gpx"
        assert move.call_args.args[1] == source.error_directory
        assert move.call_args.kwargs["filename"] == "bad.gpx"

    def test_a_failed_move_is_logged_not_raised(self):
        with (
            patch.object(bulk_entry.core_file_uploads, "move_within", side_effect=OSError("nope")),
            patch.object(bulk_entry.os, "makedirs"),
        ):
            bulk_entry._move_failed_file_to_error_directory(sources.BulkImportSource(), "/tmp/bad.gpx")


class TestProcessAllFilesSync:
    def test_processes_every_file_with_the_same_import_time(self):
        with (
            patch.object(bulk_entry.core_database, "get_db", return_value=iter([MagicMock()])),
            patch.object(bulk_entry, "ingestion_jobs_crud"),
            patch.object(bulk_entry, "store_activity_file") as store,
        ):
            bulk_entry.process_all_files_sync(7, [("job-a", "/a.gpx"), ("job-b", "/b.fit")], "2026-07-21T00:00:00")

        assert store.call_count == 2
        assert [call.args[1] for call in store.call_args_list] == ["/a.gpx", "/b.fit"]
        assert all(
            call.kwargs["source"].import_initiated_time == "2026-07-21T00:00:00" for call in store.call_args_list
        )

    def test_each_file_reports_its_own_terminal_state(self):
        """Nothing retries on this path, so the handle must end resolved either way."""
        created = MagicMock(id=11)
        with (
            patch.object(bulk_entry.core_database, "get_db", return_value=iter([MagicMock()])),
            patch.object(bulk_entry, "ingestion_jobs_crud") as jobs,
            patch.object(bulk_entry, "store_activity_file", side_effect=[[created], None]),
        ):
            bulk_entry.process_all_files_sync(7, [("job-a", "/a.gpx"), ("job-b", "/b.fit")], "2026-07-21T00:00:00")

        assert [call.args[0] for call in jobs.mark_processing.call_args_list] == ["job-a", "job-b"]
        assert jobs.mark_completed.call_args.args[:2] == ("job-a", [11])
        assert jobs.mark_failed.call_args.args[0] == "job-b"
