"""Tests for the activity-ingestion bulk-import route branching."""

from unittest.mock import MagicMock, patch

import modules.activities.activity_ingestion.router as router


def _run_route(db):
    return router.create_activity_with_bulk_import(token_user_id=3, _check_scopes=None, db=db)


class TestBulkImportRoute:
    def test_enqueues_one_durable_job_per_file_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["a.gpx", "b.fit"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_file") as publish,
            patch.object(router, "executor") as executor,
        ):
            result = _run_route(db)

        assert result["detail"]
        assert publish.call_count == 2
        # Each call publishes (file_path, user_id, import_time, db).
        for call in publish.call_args_list:
            assert call.args[1] == 3
            assert call.args[3] is db
        executor.submit.assert_not_called()

    def test_falls_back_to_threadpool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", False),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["a.gpx"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_file") as publish,
            patch.object(router, "executor") as executor,
        ):
            result = _run_route(db)

        assert result["detail"]
        publish.assert_not_called()
        executor.submit.assert_called_once()

    def test_skips_unsupported_extensions(self):
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["notes.txt"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_file") as publish,
            patch.object(router, "executor"),
        ):
            _run_route(db)

        publish.assert_not_called()
