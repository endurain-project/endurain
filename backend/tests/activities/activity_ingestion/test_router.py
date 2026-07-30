"""Tests for the activity-ingestion bulk-import route branching."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.router as router
import modules.activities.activity_ingestion.schema as activity_ingestion_schema


def _upload_job(**overrides):
    """Build a pending upload job for the route tests."""
    now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=UTC)
    defaults = {
        "id": "job-1",
        "filename": "ride.gpx",
        "status": activity_ingestion_schema.UploadJobStatus.PENDING,
        "created_at": now,
        "updated_at": now,
    }
    return activity_ingestion_schema.ActivityUploadJob(**{**defaults, **overrides})


def _run_route(db):
    return router.create_activity_with_bulk_import(request=MagicMock(), token_user_id=3, _check_scopes=None, db=db)


class TestBulkImportRoute:
    def test_enqueues_one_durable_job_per_file_when_jobs_enabled(self):
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["a.gpx", "b.fit"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(router.activity_ingestion_background, "submit_bulk_import") as submit,
        ):
            result = _run_route(db)

        assert result.detail
        # One batched publish for every file, staged in a single transaction.
        publish.assert_called_once()
        assert len(publish.call_args.args[0]) == 2
        assert publish.call_args.args[1] == 3
        assert publish.call_args.args[3] is db
        submit.assert_not_called()

    def test_enqueue_failure_surfaces_as_500(self):
        """A failed enqueue must not answer 202 for files that were never queued."""
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["a.gpx"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(
                router.activity_bulk_import_subscribers,
                "publish_bulk_import_files",
                side_effect=SQLAlchemyError("outbox down"),
            ),
            patch.object(router.activity_ingestion_background, "submit_bulk_import"),
            pytest.raises(HTTPException) as exc,
        ):
            _run_route(db)

        assert exc.value.status_code == 500

    def test_falls_back_to_threadpool_when_jobs_disabled(self):
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", False),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["a.gpx"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(router.activity_ingestion_background, "submit_bulk_import") as submit,
        ):
            result = _run_route(db)

        assert result.detail
        publish.assert_not_called()
        submit.assert_called_once()

    def test_skips_unsupported_extensions(self):
        db = MagicMock()
        with (
            patch.object(router.core_config.settings, "JOBS_ENABLED", True),
            patch.object(router.os, "makedirs"),
            patch.object(router.os, "listdir", return_value=["notes.txt"]),
            patch.object(router.os.path, "isfile", return_value=True),
            patch.object(router.core_file_uploads, "validate_local_file_sync"),
            patch.object(router.activity_bulk_import_subscribers, "publish_bulk_import_files") as publish,
            patch.object(router.activity_ingestion_background, "submit_bulk_import"),
        ):
            _run_route(db)

        # Nothing valid to queue -> an empty batch is still published so the
        # request commits exactly once either way.
        assert publish.call_args.args[0] == []


class TestUploadRoute:
    def test_delegates_to_upload_jobs(self):
        db = MagicMock()
        file = MagicMock()
        job = _upload_job()
        with patch.object(router.upload_jobs, "accept_upload") as accept:
            accept.return_value = job
            result = router.create_activity_with_uploaded_file(
                request=MagicMock(),
                token_user_id=7,
                file=file,
                _check_scopes=None,
                db=db,
            )

        accept.assert_called_once_with(7, file, db)
        assert result == job

    def test_http_upload_returns_202_with_job_handle(self):
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
            router.upload_jobs,
            "accept_upload",
            return_value=_upload_job(),
        ) as accept:
            client = TestClient(app)
            response = client.post(
                "/activities/upload",
                files={"file": ("ride.gpx", b"<gpx/>", "application/gpx+xml")},
            )

        # 202, not 201: the parse has been queued, not performed.
        assert response.status_code == 202
        body = response.json()
        assert body["id"] == "job-1"
        assert body["status"] == "pending"
        # The activity is attributed to the authenticated user, not any body field.
        assert accept.call_args.args[0] == 7

    def test_status_route_is_scoped_to_the_caller(self):
        db = MagicMock()
        with (
            patch.object(router.upload_crud, "get_upload_job", return_value=None) as get_job,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            router.get_activity_upload_job(
                job_id="someone-elses-job",
                token_user_id=7,
                _check_scopes=None,
                db=db,
            )

        # The owner is part of the lookup, so another user's job is simply absent
        # rather than being fetched and then rejected.
        get_job.assert_called_once_with("someone-elses-job", 7, db)

    def test_status_route_returns_the_job(self):
        db = MagicMock()
        job = _upload_job()
        with patch.object(router.upload_crud, "get_upload_job", return_value=job):
            result = router.get_activity_upload_job(
                job_id="job-1",
                token_user_id=7,
                _check_scopes=None,
                db=db,
            )

        assert result == job
