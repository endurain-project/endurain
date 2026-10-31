"""Tests for the activity-ingestion bulk-import route branching."""

from datetime import UTC, datetime
from unittest.mock import ANY, MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.router as router
import modules.activities.activity_ingestion.schema as activity_ingestion_schema


def _upload_job(**overrides):
    """Build a pending upload job for the route tests."""
    now = datetime(2026, 7, 28, 10, 0, 0, tzinfo=UTC)
    defaults = {
        "id": "job-1",
        "kind": activity_ingestion_constants.IngestionJobKind.UPLOAD,
        "filename": "ride.gpx",
        "status": activity_ingestion_constants.IngestionJobStatus.PENDING,
        "created_at": now,
        "updated_at": now,
    }
    return activity_ingestion_schema.ActivityIngestionJobRead(**{**defaults, **overrides})


class TestUploadRoute:
    def test_delegates_to_upload_jobs(self):
        db = MagicMock()
        file = MagicMock()
        job = _upload_job()
        with patch.object(router.activity_ingestion_service, "accept_upload") as accept:
            accept.return_value = job
            result = router.create_activity_with_uploaded_file(
                request=MagicMock(),
                token_user_id=7,
                file=file,
                _check_scopes=None,
                db=db,
                storage="storage",
                idempotency_key="key-1",
            )

        accept.assert_called_once_with(7, file.filename, ANY, "storage", db, idempotency_key="key-1")
        # The service never sees the upload itself: only the shared writer, bound to it.
        save_upload = accept.call_args.args[2]
        assert save_upload.func is router.core_file_uploads.save_validated_upload_sync
        assert save_upload.args == (file,)
        assert result == job

    def test_the_idempotency_key_is_optional(self):
        db = MagicMock()
        with patch.object(router.activity_ingestion_service, "accept_upload", return_value=_upload_job()) as accept:
            router.create_activity_with_uploaded_file(
                request=MagicMock(),
                token_user_id=7,
                file=MagicMock(),
                _check_scopes=None,
                db=db,
                storage="storage",
            )

        assert accept.call_args.kwargs["idempotency_key"] is None

    def test_http_upload_returns_202_with_job_handle(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.database as core_db
        import core.dependencies as core_dependencies
        import modules.auth.dependencies as auth_dependencies

        db = MagicMock()
        app = FastAPI()
        app.include_router(router.api_upload_router, prefix="/activities")
        app.dependency_overrides[core_db.get_db] = lambda: db
        app.dependency_overrides[core_dependencies.get_storage] = lambda: "storage"
        app.dependency_overrides[auth_dependencies.get_user_id_from_auth] = lambda: 7
        app.dependency_overrides[auth_dependencies.check_auth_scopes] = lambda: None

        with patch.object(
            router.activity_ingestion_service,
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
                router.activity_ingestion_service,
                "get_job",
                side_effect=core_exceptions.NotFoundError("Upload job not found"),
            ) as get_job,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            router.read_activity_ingestion_job(
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
        with patch.object(router.activity_ingestion_service, "get_job", return_value=job):
            result = router.read_activity_ingestion_job(
                job_id="job-1",
                token_user_id=7,
                _check_scopes=None,
                db=db,
            )

        assert result == job


class TestBulkImportRoutesDelegate:
    """The routes are transport adapters: they delegate and shape the response."""

    def test_the_archive_route_hands_the_upload_to_the_service_unread(self):
        db = MagicMock()
        file = MagicMock()
        job = MagicMock()
        with patch.object(router.activity_ingestion_bulk_import_service, "accept_archive", return_value=job) as accept:
            result = router.create_bulk_import_from_archive(
                request=MagicMock(),
                token_user_id=3,
                file=file,
                _check_scopes=None,
                db=db,
                storage="storage",
                source="strava",
            )

        accept.assert_called_once_with(3, file.filename, ANY, "strava", "storage", db)
        # The service never sees the upload itself: only the shared writer, bound to it.
        save_upload = accept.call_args.args[2]
        assert save_upload.func is router.core_file_uploads.save_validated_upload_sync
        assert save_upload.args == (file,)
        assert result == job

    def test_the_folder_route_delegates_with_the_callers_id_and_source(self):
        db = MagicMock()
        with patch.object(
            router.activity_ingestion_bulk_import_service, "start_from_directory", return_value="job"
        ) as start:
            result = router.create_bulk_import_from_folder(
                request=MagicMock(), token_user_id=3, _check_scopes=None, db=db, storage="storage", source="generic"
            )

        start.assert_called_once_with(3, "generic", "storage", db)
        assert result == "job"

    def test_a_service_refusal_is_not_swallowed(self):
        """A second import while one runs must reach the client as the conflict it is."""
        with (
            patch.object(
                router.activity_ingestion_bulk_import_service,
                "start_from_directory",
                side_effect=core_exceptions.ConflictError(),
            ),
            pytest.raises(core_exceptions.ConflictError),
        ):
            router.create_bulk_import_from_folder(
                request=MagicMock(), token_user_id=3, _check_scopes=None, db=MagicMock(), storage="s", source="generic"
            )
