"""Every ``202`` names the job it started and when to poll it, and a refused second start names the running job.

The routers are mounted under the prefixes the application uses, with their services patched, so the
assertions read what a client sees: the ``Content-Location`` path, ``Retry-After``, and the 409 that names the
running job. Reading a job, and its ``Retry-After`` while it runs, is tested with the job routes.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.router as activity_router
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.router as ingestion_router
import modules.activities.activity_ingestion.schema as ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.garmin.constants as garmin_constants
import modules.garmin.router as garmin_router
import modules.garmin.schema as garmin_schema
import modules.jobs.router as jobs_router
import modules.strava.constants as strava_constants
import modules.strava.router as strava_router
import modules.strava.schema as strava_schema
import modules.users.users.constants as users_constants
import modules.users.users.router as users_router
import modules.users.users.schema as users_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.router as profile_router
import modules.users.users_profile.schema as profile_schema

_JOB_ID = "0c0f8e0e-3f0b-4a50-9a58-6a1d0a2d5d11"
_NOW = datetime(2026, 11, 5, 7, 30, tzinfo=UTC)
_DAYS = {"start_date": "2026-01-01", "end_date": "2026-01-08"}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(ingestion_router.router, prefix="/activities")
    app.include_router(activity_router.router, prefix="/activities")
    app.include_router(garmin_router.router, prefix="/garmin")
    app.include_router(strava_router.router, prefix="/strava")
    app.include_router(users_router.router, prefix="/users")
    app.include_router(profile_router.router, prefix="/profile")
    app.include_router(jobs_router.router, prefix="/jobs")
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[core_dependencies.get_storage] = lambda: "storage"
    app.dependency_overrides[auth_dependencies.get_current_user_id] = lambda: 7
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: "session"
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[core_dependencies.require_if_match_header] = lambda: '"1"'
    return TestClient(app)


def _job(
    kind: ingestion_constants.IngestionJobKind = ingestion_constants.IngestionJobKind.UPLOAD,
) -> ingestion_schema.ActivityIngestionJobRead:
    return ingestion_schema.ActivityIngestionJobRead(
        id=_JOB_ID, kind=f"activity_{kind.value}", status=_QUEUED, created_at=_NOW, updated_at=_NOW
    )


def _envelope(kind: str, status: core_job_status.JobState = core_job_status.JobState.QUEUED) -> dict[str, object]:
    return {"id": _JOB_ID, "kind": kind, "status": status, "created_at": _NOW}


_JOB_STATUS = f"/jobs/{_JOB_ID}"
_UPLOAD = ingestion_constants.IngestionJobKind.UPLOAD
_BULK = ingestion_constants.IngestionJobKind.BULK_IMPORT
_REFRESH = ingestion_constants.IngestionJobKind.REFRESH
_QUEUED = core_job_status.JobState.QUEUED
_RUNNING = core_job_status.JobState.RUNNING

#: ``(id, request, service to patch, what it returns, Content-Location, Retry-After)`` of every 202 that names a status.
_ACCEPTING_ROUTES = [
    pytest.param(
        ("POST", "/activities/upload", {"files": {"file": ("ride.gpx", b"<gpx/>")}}),
        (ingestion_router.activity_ingestion_service, "accept_upload"),
        _job(_UPLOAD),
        _JOB_STATUS,
        ingestion_constants.JOB_POLL_SECONDS[_UPLOAD],
        id="upload",
    ),
    pytest.param(
        ("POST", "/activities/bulk-import", {"files": {"file": ("export.zip", b"PK")}}),
        (ingestion_router.activity_ingestion_bulk_import_service, "accept_archive"),
        _job(_BULK),
        _JOB_STATUS,
        ingestion_constants.JOB_POLL_SECONDS[_BULK],
        id="bulk-import",
    ),
    pytest.param(
        ("POST", "/activities/bulk-import/folder", {}),
        (ingestion_router.activity_ingestion_bulk_import_service, "start_from_directory"),
        _job(_BULK),
        _JOB_STATUS,
        ingestion_constants.JOB_POLL_SECONDS[_BULK],
        id="bulk-import-folder",
    ),
    pytest.param(
        ("POST", "/activities/refresh", {}),
        (ingestion_router.activity_ingestion_service, "accept_refresh"),
        _job(_REFRESH),
        _JOB_STATUS,
        ingestion_constants.JOB_POLL_SECONDS[_REFRESH],
        id="refresh",
    ),
    pytest.param(
        ("POST", "/garmin/activities", {"params": _DAYS}),
        (garmin_router.garmin_sync_service, "request_activities_sync"),
        _job(_REFRESH),
        _JOB_STATUS,
        ingestion_constants.JOB_POLL_SECONDS[_REFRESH],
        id="garmin-activities",
    ),
    pytest.param(
        ("POST", "/strava/activities", {"params": _DAYS}),
        (strava_router.strava_sync_service, "request_activities_sync"),
        _job(_REFRESH),
        _JOB_STATUS,
        ingestion_constants.JOB_POLL_SECONDS[_REFRESH],
        id="strava-activities",
    ),
    pytest.param(
        ("POST", "/garmin/link", {"json": {"username": "me", "password": "secret"}}),
        (garmin_router.garmin_link_service, "start_link"),
        garmin_schema.GarminLinkStatus.model_validate(_envelope("garmin_link", _RUNNING)),
        _JOB_STATUS,
        garmin_constants.LINK_POLL_SECONDS,
        id="garmin-link",
    ),
    pytest.param(
        ("POST", "/garmin/gear", {}),
        (garmin_router.garmin_sync_service, "request_gear_sync"),
        garmin_schema.GarminSyncStatus.model_validate(_envelope("garmin_sync_gear")),
        _JOB_STATUS,
        garmin_constants.SYNC_POLL_SECONDS,
        id="garmin-gear",
    ),
    pytest.param(
        ("POST", "/garmin/health", {"params": _DAYS}),
        (garmin_router.garmin_sync_service, "request_health_sync"),
        garmin_schema.GarminSyncStatus.model_validate(_envelope("garmin_sync_health")),
        _JOB_STATUS,
        garmin_constants.SYNC_POLL_SECONDS,
        id="garmin-health",
    ),
    pytest.param(
        ("POST", "/strava/link", {"json": {"state": "s" * 32, "code": "c", "scope": "read"}}),
        (strava_router.strava_link_service, "start_link"),
        strava_schema.StravaSyncStatus.model_validate(_envelope("strava_link")),
        _JOB_STATUS,
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.LINK],
        id="strava-link",
    ),
    pytest.param(
        ("POST", "/strava/gear", {}),
        (strava_router.strava_sync_service, "request_gear_sync"),
        strava_schema.StravaSyncStatus.model_validate(_envelope("strava_gear")),
        _JOB_STATUS,
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR],
        id="strava-gear",
    ),
    pytest.param(
        ("DELETE", "/strava/link", {}),
        (strava_router.strava_sync_service, "request_unlink"),
        strava_schema.StravaSyncStatus.model_validate(_envelope("strava_unlink")),
        _JOB_STATUS,
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.UNLINK],
        id="strava-unlink",
    ),
    pytest.param(
        ("POST", f"/users/{uuid.uuid4()}/delete", {"json": {"step_up": {"current_password": "secret"}}}),
        (users_router.users_deletion_job_service, "request_deletion_by_administrator"),
        users_schema.UserDeletionStatus.model_validate(_envelope("user_deletion")),
        _JOB_STATUS,
        users_constants.DELETION_POLL_SECONDS,
        id="user-deletion",
    ),
    pytest.param(
        ("POST", "/profile/export", {"json": {"step_up": {"current_password": "secret"}}}),
        (profile_router.profile_export_job_service, "request_export"),
        profile_schema.ProfileExportStatus.model_validate(_envelope("profile_export")),
        _JOB_STATUS,
        profile_constants.EXPORT_POLL_SECONDS,
        id="profile-export",
    ),
    pytest.param(
        ("POST", "/profile/import", {"files": {"file": ("export.zip", b"PK")}}),
        (profile_router.profile_import_job_service, "request_import"),
        profile_schema.ProfileImportStatus.model_validate(_envelope("profile_import")),
        _JOB_STATUS,
        profile_constants.IMPORT_POLL_SECONDS,
        id="profile-import",
    ),
    pytest.param(
        ("PATCH", "/activities", {"json": {"visibility": "private"}}),
        (activity_router.activity_bulk_edit_job_service, "request_visibility_edit"),
        activity_schema.ActivitiesBulkEditStatus.model_validate(_envelope("activities_bulk_edit")),
        _JOB_STATUS,
        bulk_edit_constants.BULK_EDIT_POLL_SECONDS,
        id="bulk-edit",
    ),
]


@pytest.mark.parametrize(("call", "service", "accepted", "location", "retry_after"), _ACCEPTING_ROUTES)
def test_a_202_names_its_job_and_when_to_poll_it(client, call, service, accepted, location, retry_after):
    method, path, kwargs = call
    with patch.object(*service, return_value=accepted):
        response = client.request(method, path, **kwargs)

    assert response.status_code == 202, response.text
    assert response.headers["Content-Location"] == location
    assert response.headers["Retry-After"] == str(retry_after)


def test_an_account_deletion_by_its_owner_names_no_job_to_read(client):
    with (
        patch.object(
            profile_router.profile_service,
            "delete_account",
            return_value=users_schema.UserDeletionStatus.model_validate(_envelope("user_deletion")),
        ),
        patch.object(profile_router.authentication_dependencies, "clear_refresh_token_cookies"),
    ):
        response = client.post("/profile/delete-account", json={"step_up": {"current_password": "secret"}})

    assert response.status_code == 202, response.text
    assert "Content-Location" not in response.headers


class TestARefusedSecondRun:
    def test_a_bulk_import_conflict_names_the_running_job(self, client):
        running = core_exceptions.JobAlreadyRunningError("A bulk import is already running", job_id=_JOB_ID)
        with patch.object(
            ingestion_router.activity_ingestion_bulk_import_service, "accept_archive", side_effect=running
        ):
            response = client.post("/activities/bulk-import", files={"file": ("export.zip", b"PK")})

        assert response.status_code == 409
        assert response.headers["Content-Location"] == _JOB_STATUS
        assert response.headers["Content-Type"].startswith("application/problem+json")
        body = response.json()
        assert body["type"].endswith(":conflict")
        assert body["job_id"] == _JOB_ID

    def test_a_sync_conflict_names_the_running_job(self, client):
        running = core_exceptions.JobAlreadyRunningError(
            "A Garmin Connect gear sync is already in progress", job_id=_JOB_ID
        )
        with patch.object(garmin_router.garmin_sync_service, "request_gear_sync", side_effect=running):
            response = client.post("/garmin/gear")

        assert response.status_code == 409
        assert response.headers["Content-Location"] == _JOB_STATUS
        assert response.json()["job_id"] == _JOB_ID

    def test_a_conflict_over_a_job_that_cannot_be_named_carries_no_location(self, client):
        running = core_exceptions.JobAlreadyRunningError(
            "A Garmin Connect gear sync is already in progress", job_id=None
        )
        with patch.object(garmin_router.garmin_sync_service, "request_gear_sync", side_effect=running):
            response = client.post("/garmin/gear")

        assert response.status_code == 409
        assert "Content-Location" not in response.headers
        assert "job_id" not in response.json()

    def test_a_plain_conflict_carries_no_location(self, client):
        with patch.object(
            ingestion_router.activity_ingestion_bulk_import_service,
            "start_from_directory",
            side_effect=core_exceptions.ConflictError("A bulk import is already running"),
        ):
            response = client.post("/activities/bulk-import/folder")

        assert response.status_code == 409
        assert "Content-Location" not in response.headers
