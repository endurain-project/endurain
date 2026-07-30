"""Tests for the activity_ingestion orchestrator.

Covers the parser-aware ingestion flow (``parse_file``,
``_prepare_bulk_import_activity``, the store/upload entry points). The generic
file plumbing it used to own — gzip expansion, content hashing, artifact cleanup
— now lives in ``core.file_uploads`` and is tested there.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestPrepareBulkImportActivity:
    def test_returns_activity_if_not_bulk_import(self):
        from modules.activities.activity_ingestion.orchestrator import _prepare_bulk_import_activity

        activity = MagicMock()
        result = _prepare_bulk_import_activity(
            activity,
            is_bulk_import=False,
            created_activities_objects=[],
            strava_activities=None,
            activity_metadata_dict={},
        )

        assert result is activity

    @patch("modules.activities.activity_ingestion.orchestrator.strava_bulk_import_utils")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_skips_duplicate_in_multi_activity_fit(self, mock_logger, mock_strava):
        from modules.activities.activity_ingestion.orchestrator import _prepare_bulk_import_activity

        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = False

        activity = MagicMock()
        result = _prepare_bulk_import_activity(
            activity,
            is_bulk_import=True,
            created_activities_objects=[MagicMock(), MagicMock()],
            strava_activities={"some": "data"},
            activity_metadata_dict={"metadata_found_in_csv": True},
        )

        assert result is None
        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.assert_called_once()

    @patch("modules.activities.activity_ingestion.orchestrator.strava_bulk_import_utils")
    def test_appends_metadata_for_bulk_import(self, mock_strava):
        from modules.activities.activity_ingestion.orchestrator import _prepare_bulk_import_activity

        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = True
        mock_strava.append_bulk_import_metadata_to_activity.side_effect = lambda a, m: a

        activity = MagicMock()
        result = _prepare_bulk_import_activity(
            activity,
            is_bulk_import=True,
            created_activities_objects=[MagicMock()],
            strava_activities={"some": "data"},
            activity_metadata_dict={"metadata_found_in_csv": True},
        )

        assert result is activity
        mock_strava.append_bulk_import_metadata_to_activity.assert_called_once()


class TestParseFile:
    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_parse_gpx(self, mock_logger, mock_gpx):
        from modules.activities.activity_ingestion.orchestrator import parse_file

        mock_gpx.parse_gpx_file.return_value = {"activity": "data"}
        result = parse_file(
            token_user_id=1,
            file_extension=".gpx",
            filename="/path/to/file.gpx",
        )
        assert result == {"activity": "data"}

    @patch("modules.activities.activity_file_import.registry.tcx_utils")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_parse_tcx(self, mock_logger, mock_tcx):
        from modules.activities.activity_ingestion.orchestrator import parse_file

        mock_tcx.parse_tcx_file.return_value = {"activity": "tcx_data"}
        result = parse_file(
            token_user_id=1,
            file_extension=".tcx",
            filename="/path/to/file.tcx",
        )
        assert result == {"activity": "tcx_data"}

    @patch("modules.activities.activity_file_import.registry.fit_utils")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_parse_fit(self, mock_logger, mock_fit):
        from modules.activities.activity_ingestion.orchestrator import parse_file

        mock_fit.parse_fit_file.return_value = {"activity": "fit_data"}
        result = parse_file(
            token_user_id=1,
            file_extension=".fit",
            filename="/path/to/file.fit",
        )
        assert result == {"activity": "fit_data"}

    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_raises_on_unsupported_extension(self, mock_logger):
        from fastapi import HTTPException

        from modules.activities.activity_ingestion.orchestrator import parse_file

        with pytest.raises(HTTPException) as exc:
            parse_file(
                token_user_id=1,
                file_extension=".xyz",
                filename="/path/to/file.xyz",
            )
        assert exc.value.status_code == 406

    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_returns_none_for_bulk_import_init(self, mock_logger):
        from modules.activities.activity_ingestion.orchestrator import parse_file

        result = parse_file(
            token_user_id=1,
            file_extension=".py",
            filename="bulk_import/__init__.py",
        )
        assert result is None


class TestParseFileError:
    """Exception handler in parse_file."""

    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_raises_500_on_parse_error(self, mock_logger, mock_gpx):
        from fastapi import HTTPException

        from modules.activities.activity_ingestion.orchestrator import parse_file

        mock_gpx.parse_gpx_file.side_effect = ValueError("bad data")

        with pytest.raises(HTTPException) as exc:
            parse_file(
                token_user_id=1,
                file_extension=".gpx",
                filename="/path/to/file.gpx",
            )
        assert exc.value.status_code == 500


class TestStoreBulkImportFile:
    """The raising per-file body for the durable bulk-import job."""

    def test_delegates_to_raising_core_as_bulk_import(self):
        from modules.activities.activity_ingestion import orchestrator

        with patch.object(orchestrator, "_validate_prepare_and_store_file", return_value=["activity"]) as helper:
            result = orchestrator.store_bulk_import_file(3, "/tmp/x.gpx", "2026-07-21T00:00:00", "db")

        helper.assert_called_once_with(
            3, "/tmp/x.gpx", "db", is_bulk_import=True, import_initiated_time="2026-07-21T00:00:00"
        )
        assert result == ["activity"]

    def test_propagates_failure_instead_of_swallowing(self):
        from modules.activities.activity_ingestion import orchestrator

        with (
            patch.object(orchestrator, "_validate_prepare_and_store_file", side_effect=ValueError("boom")),
            pytest.raises(ValueError),
        ):
            orchestrator.store_bulk_import_file(3, "/tmp/x.gpx", "2026-07-21T00:00:00", "db")
