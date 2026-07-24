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


class TestUploadRoute:
    def test_delegates_to_orchestrator(self):
        db = MagicMock()
        file = MagicMock()
        with patch.object(router.orchestrator, "parse_and_store_activity_from_uploaded_file") as store:
            store.return_value = ["activity"]
            result = router.create_activity_with_uploaded_file(
                token_user_id=7,
                file=file,
                _check_scopes=None,
                db=db,
            )

        store.assert_called_once_with(7, file, db)
        assert result == ["activity"]

    def test_http_upload_success(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.database as core_db
        import modules.auth.dependencies as auth_dependencies

        db = MagicMock()
        app = FastAPI()
        app.include_router(router.api_upload_router, prefix="/activities")
        app.dependency_overrides[core_db.get_db] = lambda: db
        app.dependency_overrides[auth_dependencies.get_user_id_from_auth] = lambda: 7
        app.dependency_overrides[auth_dependencies.check_auth_scopes] = lambda: None

        with patch.object(
            router.orchestrator,
            "parse_and_store_activity_from_uploaded_file",
            return_value=[],
        ) as store:
            client = TestClient(app)
            response = client.post(
                "/activities/upload",
                files={"file": ("ride.gpx", b"<gpx/>", "application/gpx+xml")},
            )

        assert response.status_code == 201
        assert response.json() == []
        # The activity is attributed to the authenticated user, not any body field.
        assert store.call_args.args[0] == 7
