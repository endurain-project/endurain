"""Tests for the activity_ingestion orchestrator.

Moved from ``tests/activities/activity/test_utils_extra.py`` when the parser-aware
ingestion flow (``handle_gzipped_file``, ``parse_file``, ``_prepare_bulk_import_activity``,
``_cleanup_upload_artifacts``) relocated out of ``activity/utils.py`` into
``activity_ingestion/orchestrator.py``.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestSha256File:
    def test_matches_hashlib(self, tmp_path):
        import hashlib

        import modules.activities.activity_ingestion.orchestrator as orchestrator

        path = tmp_path / "activity.gpx"
        payload = b"<gpx>some deterministic content</gpx>"
        path.write_bytes(payload)

        assert orchestrator._sha256_file(str(path)) == hashlib.sha256(payload).hexdigest()

    def test_stable_across_reads(self, tmp_path):
        import modules.activities.activity_ingestion.orchestrator as orchestrator

        path = tmp_path / "activity.fit"
        path.write_bytes(b"\x00\x01\x02repeatable\xff")

        # The same file bytes must hash identically on every read (the property
        # that makes re-importing the same file a no-op).
        assert orchestrator._sha256_file(str(path)) == orchestrator._sha256_file(str(path))


class TestHandleGzippedFile:
    @patch("modules.activities.activity_ingestion.orchestrator.gzip.open")
    @patch("modules.activities.activity_ingestion.orchestrator.NamedTemporaryFile")
    @patch("modules.activities.activity_ingestion.orchestrator.core_file_uploads")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    @patch("modules.activities.activity_ingestion.orchestrator.Path")
    def test_handle_decompresses_successfully(
        self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open
    ):
        from modules.activities.activity_ingestion.orchestrator import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity_123.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "activity_123.fit.gz"
        mock_path = mock_path_cls.return_value

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmpabc123.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gz = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_gz
        mock_gz.read.side_effect = [b"some data", b""]

        result_path, result_ext = handle_gzipped_file("/uploads/activity_123.fit.gz")

        assert result_path == "/safe/tmp/tmpabc123.fit"
        assert result_ext == ".fit"
        mock_gzip_open.assert_called_once_with(mock_path, "rb")

    @patch("modules.activities.activity_ingestion.orchestrator.gzip.open")
    @patch("modules.activities.activity_ingestion.orchestrator.NamedTemporaryFile")
    @patch("modules.activities.activity_ingestion.orchestrator.core_file_uploads")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    @patch("modules.activities.activity_ingestion.orchestrator.Path")
    def test_handle_invalid_gzip_raises_400(self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open):
        from fastapi import HTTPException

        from modules.activities.activity_ingestion.orchestrator import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity_123.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "bad.gz"

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmpabc.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gzip_open.return_value.__enter__.side_effect = EOFError("Not a gzip file")

        with pytest.raises(HTTPException) as exc:
            handle_gzipped_file("/uploads/bad.gz")
        assert exc.value.status_code == 400

    @patch("modules.activities.activity_ingestion.orchestrator.gzip.open")
    @patch("modules.activities.activity_ingestion.orchestrator.NamedTemporaryFile")
    @patch("modules.activities.activity_ingestion.orchestrator.core_file_uploads")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    @patch("modules.activities.activity_ingestion.orchestrator.Path")
    def test_handle_exceeds_max_size_raises_413(
        self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open
    ):
        from fastapi import HTTPException

        import modules.activities.activity_ingestion.orchestrator as orchestrator
        from modules.activities.activity_ingestion.orchestrator import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity_123.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "big.gz"

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmpabc.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gz = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_gz
        chunk = b"x" * 1024 * 1024
        mock_gz.read.side_effect = [chunk, chunk, b""]

        orig_max = orchestrator._MAX_DECOMPRESSED_ACTIVITY_BYTES
        orchestrator._MAX_DECOMPRESSED_ACTIVITY_BYTES = 1

        with pytest.raises(HTTPException) as exc:
            handle_gzipped_file("/uploads/big.gz")
        orchestrator._MAX_DECOMPRESSED_ACTIVITY_BYTES = orig_max
        assert exc.value.status_code == 413


class TestCleanupUploadArtifacts:
    @patch("modules.activities.activity_ingestion.orchestrator.os")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_removes_existing_files(self, mock_logger, mock_os):
        from modules.activities.activity_ingestion.orchestrator import _cleanup_upload_artifacts

        mock_os.path.isfile.side_effect = lambda p: p in ["/safe/tmp/a", "/safe/tmp/b"]

        _cleanup_upload_artifacts(["/safe/tmp/a", "/safe/tmp/b", "/safe/tmp/c"])

        assert mock_os.remove.call_count == 2
        mock_os.remove.assert_any_call("/safe/tmp/a")
        mock_os.remove.assert_any_call("/safe/tmp/b")

    @patch("modules.activities.activity_ingestion.orchestrator.os")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    def test_logs_warning_on_oserror(self, mock_logger, mock_os):
        from modules.activities.activity_ingestion.orchestrator import _cleanup_upload_artifacts

        mock_os.path.isfile.return_value = True
        mock_os.remove.side_effect = OSError("Permission denied")

        _cleanup_upload_artifacts(["/safe/tmp/a"])

        mock_logger.print_to_log.assert_called_once()


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
    @patch("modules.activities.activity_ingestion.orchestrator.gpx_utils")
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

    @patch("modules.activities.activity_ingestion.orchestrator.tcx_utils")
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

    @patch("modules.activities.activity_ingestion.orchestrator.fit_utils")
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


class TestHandleGzippedFileCleanup:
    """Cleanup on EOFError during read (temp_file_path set)."""

    @patch("modules.activities.activity_ingestion.orchestrator.gzip.open")
    @patch("modules.activities.activity_ingestion.orchestrator.NamedTemporaryFile")
    @patch("modules.activities.activity_ingestion.orchestrator.core_file_uploads")
    @patch("modules.activities.activity_ingestion.orchestrator.core_logger")
    @patch("modules.activities.activity_ingestion.orchestrator.Path")
    def test_cleanup_on_eof_during_read(self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open):
        from fastapi import HTTPException

        from modules.activities.activity_ingestion.orchestrator import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "bad.gz"

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmp.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gz = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_gz
        mock_gz.read.side_effect = EOFError("corrupted read")

        with pytest.raises(HTTPException) as exc:
            handle_gzipped_file("/uploads/bad.gz")
        assert exc.value.status_code == 400


class TestParseFileError:
    """Exception handler in parse_file."""

    @patch("modules.activities.activity_ingestion.orchestrator.gpx_utils")
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
