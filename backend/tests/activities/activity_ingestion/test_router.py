"""Tests for the activity-ingestion bulk-import route branching."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.router as router
import modules.activities.activity_ingestion.schema as activity_ingestion_schema


def _upload_job(**overrides):
    """Build a pending upload job for the route tests."""
    now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=UTC)
    defaults = {
        "id": "job-1",
        "kind": activity_ingestion_schema.IngestionJobKind.UPLOAD,
        "filename": "ride.gpx",
        "status": activity_ingestion_schema.IngestionJobStatus.PENDING,
        "created_at": now,
        "updated_at": now,
    }
    return activity_ingestion_schema.ActivityIngestionJob(**{**defaults, **overrides})


class TestUploadRoute:
    def test_delegates_to_upload_jobs(self):
        db = MagicMock()
        file = MagicMock()
        job = _upload_job()
        with patch.object(router.ingestion_jobs, "accept_upload") as accept:
            accept.return_value = job
            result = router.create_activity_with_uploaded_file(
                request=MagicMock(),
                token_user_id=7,
                file=file,
                _check_scopes=None,
                db=db,
                idempotency_key="key-1",
            )

        accept.assert_called_once_with(7, file, db, idempotency_key="key-1")
        assert result == job

    def test_the_idempotency_key_is_optional(self):
        db = MagicMock()
        with patch.object(router.ingestion_jobs, "accept_upload", return_value=_upload_job()) as accept:
            router.create_activity_with_uploaded_file(
                request=MagicMock(),
                token_user_id=7,
                file=MagicMock(),
                _check_scopes=None,
                db=db,
            )

        assert accept.call_args.kwargs["idempotency_key"] is None

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
            router.ingestion_jobs,
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
            patch.object(
                router.ingestion_jobs, "get_job", side_effect=core_exceptions.NotFoundError("Upload job not found")
            ) as get_job,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            router.get_activity_ingestion_job(
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
        with patch.object(router.ingestion_jobs, "get_job", return_value=job):
            result = router.get_activity_ingestion_job(
                job_id="job-1",
                token_user_id=7,
                _check_scopes=None,
                db=db,
            )

        assert result == job


class TestBulkImportRouteDelegates:
    """The route is a transport adapter: it delegates and shapes the response."""

    def test_delegates_to_the_service_and_returns_the_job_handles(self):
        db = MagicMock()
        jobs = [MagicMock(), MagicMock()]
        with patch.object(router.bulk_import_service, "start_bulk_import", return_value=jobs) as start:
            result = router.create_activity_with_bulk_import(
                request=MagicMock(), token_user_id=3, _check_scopes=None, db=db
            )

        start.assert_called_once_with(3, db)
        # One pollable handle per queued file, so the caller can follow the
        # import instead of being handed a message it cannot act on.
        assert result == jobs

    def test_a_service_failure_is_not_swallowed(self):
        """The route must not answer 202 for files that were never queued."""
        with (
            patch.object(
                router.bulk_import_service, "start_bulk_import", side_effect=core_exceptions.ProcessingError()
            ),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            router.create_activity_with_bulk_import(
                request=MagicMock(), token_user_id=3, _check_scopes=None, db=MagicMock()
            )
