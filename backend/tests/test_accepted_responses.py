"""Every ``202`` names the status resource to poll, and a status read asks for another poll while it runs.

The routers are mounted under the prefixes the application uses, with their services patched, so the
assertions read what a client sees: the ``Content-Location`` path, ``Retry-After``, and the 409 that names the
running job.
"""

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
import modules.strava.constants as strava_constants
import modules.strava.router as strava_router
import modules.strava.schema as strava_schema
import modules.users.users.constants as users_constants
import modules.users.users.router as users_router
import modules.users.users.schema as users_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.import_state_store as profile_import_state_store
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
    app.include_router(ingestion_router.api_upload_router, prefix="/activities")
    app.include_router(activity_router.router, prefix="/activities")
    app.include_router(garmin_router.router, prefix="/garmin")
    app.include_router(strava_router.router, prefix="/strava")
    app.include_router(users_router.router, prefix="/users")
    app.include_router(profile_router.router, prefix="/profile")
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[core_dependencies.get_storage] = lambda: "storage"
    app.dependency_overrides[auth_dependencies.get_user_id_from_auth] = lambda: 7
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 7
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: "session"
    app.dependency_overrides[auth_dependencies.check_auth_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[core_dependencies.require_if_match_header] = lambda: '"1"'
    return TestClient(app)


def _job(
    kind: ingestion_constants.IngestionJobKind = ingestion_constants.IngestionJobKind.UPLOAD,
    status: core_job_status.JobState = core_job_status.JobState.QUEUED,
) -> ingestion_schema.ActivityIngestionJobRead:
    return ingestion_schema.ActivityIngestionJobRead(
        id=_JOB_ID, kind=kind, status=status, created_at=_NOW, updated_at=_NOW
    )


_JOB_STATUS = f"/activities/ingestion-jobs/{_JOB_ID}"
_UPLOAD = ingestion_constants.IngestionJobKind.UPLOAD
_BULK = ingestion_constants.IngestionJobKind.BULK_IMPORT
_REFRESH = ingestion_constants.IngestionJobKind.REFRESH
_QUEUED = core_job_status.JobState.QUEUED

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
        garmin_schema.GarminLinkStatus(status=core_job_status.JobState.RUNNING),
        "/garmin/link/status",
        garmin_constants.LINK_POLL_SECONDS,
        id="garmin-link",
    ),
    pytest.param(
        ("POST", "/garmin/gear", {}),
        (garmin_router.garmin_sync_service, "request_gear_sync"),
        garmin_schema.GarminSyncStatus(kind=garmin_constants.SyncKind.GEAR, status=_QUEUED),
        "/garmin/sync/gear",
        garmin_constants.SYNC_POLL_SECONDS,
        id="garmin-gear",
    ),
    pytest.param(
        ("POST", "/garmin/health", {"params": _DAYS}),
        (garmin_router.garmin_sync_service, "request_health_sync"),
        garmin_schema.GarminSyncStatus(kind=garmin_constants.SyncKind.HEALTH, status=_QUEUED),
        "/garmin/sync/health",
        garmin_constants.SYNC_POLL_SECONDS,
        id="garmin-health",
    ),
    pytest.param(
        ("POST", "/strava/link", {"json": {"state": "s" * 32, "code": "c", "scope": "read"}}),
        (strava_router.strava_link_service, "start_link"),
        strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.LINK, status=_QUEUED),
        "/strava/sync/link",
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.LINK],
        id="strava-link",
    ),
    pytest.param(
        ("POST", "/strava/gear", {}),
        (strava_router.strava_sync_service, "request_gear_sync"),
        strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.GEAR, status=_QUEUED),
        "/strava/sync/gear",
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR],
        id="strava-gear",
    ),
    pytest.param(
        ("DELETE", "/strava/link", {}),
        (strava_router.strava_sync_service, "request_unlink"),
        strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.UNLINK, status=_QUEUED),
        "/strava/sync/unlink",
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.UNLINK],
        id="strava-unlink",
    ),
    pytest.param(
        ("DELETE", "/users/12", {}),
        (users_router.users_deletion_job_service, "request_deletion_by_administrator"),
        users_schema.UserDeletionStatus(status=core_job_status.JobState.QUEUED),
        "/users/12/deletion",
        users_constants.DELETION_POLL_SECONDS,
        id="user-deletion",
    ),
    pytest.param(
        ("POST", "/profile/export", {"json": {"current_password": "secret"}}),
        (profile_router.profile_export_job_service, "request_export"),
        profile_schema.ProfileExportStatus(status=core_job_status.JobState.QUEUED),
        "/profile/export",
        profile_constants.EXPORT_POLL_SECONDS,
        id="profile-export",
    ),
    pytest.param(
        ("POST", "/profile/import", {"files": {"file": ("export.zip", b"PK")}}),
        (profile_router.profile_import_job_service, "request_import"),
        profile_import_state_store.ProfileImportState(status=profile_constants.ImportStatus.QUEUED),
        "/profile/import",
        profile_constants.IMPORT_POLL_SECONDS,
        id="profile-import",
    ),
    pytest.param(
        ("PATCH", "/activities", {"json": {"visibility": "private"}}),
        (activity_router.activity_bulk_edit_job_service, "request_visibility_edit"),
        activity_schema.ActivitiesBulkEditStatus(status=core_job_status.JobState.QUEUED),
        "/activities/bulk-edit",
        bulk_edit_constants.BULK_EDIT_POLL_SECONDS,
        id="bulk-edit",
    ),
]


@pytest.mark.parametrize(("call", "service", "accepted", "location", "retry_after"), _ACCEPTING_ROUTES)
def test_a_202_names_its_status_resource_and_when_to_poll_it(client, call, service, accepted, location, retry_after):
    method, path, kwargs = call
    with patch.object(*service, return_value=accepted):
        response = client.request(method, path, **kwargs)

    assert response.status_code == 202, response.text
    assert response.headers["Content-Location"] == location
    assert response.headers["Retry-After"] == str(retry_after)


def test_an_account_deletion_by_its_owner_has_no_status_resource_to_name(client):
    with (
        patch.object(
            profile_router.profile_service,
            "delete_account",
            return_value=users_schema.UserDeletionStatus(status=core_job_status.JobState.QUEUED),
        ),
        patch.object(profile_router.authentication_dependencies, "clear_refresh_token_cookies"),
    ):
        response = client.post("/profile/delete-account", json={"current_password": "secret"})

    assert response.status_code == 202, response.text
    assert "Content-Location" not in response.headers


_RUNNING = core_job_status.JobState.RUNNING
_DONE = core_job_status.JobState.SUCCEEDED
_FAILED = core_job_status.JobState.FAILED
_DEFERRED = core_job_status.JobState.QUEUED
_SYNC_RUNNING = core_job_status.JobState.RUNNING
_SYNC_DONE = core_job_status.JobState.SUCCEEDED
_SYNC_FAILED = core_job_status.JobState.FAILED

#: ``(request, service to patch, what it returns for a running and for a finished status, Retry-After)``.
_STATUS_ROUTES = [
    pytest.param(
        ("GET", _JOB_STATUS),
        (ingestion_router.activity_ingestion_service, "get_job"),
        [_job(_BULK, _RUNNING), _job(_BULK, _DEFERRED)],
        [_job(_BULK, _DONE), _job(_BULK, _FAILED)],
        ingestion_constants.JOB_POLL_SECONDS[_BULK],
        id="ingestion-job",
    ),
    pytest.param(
        ("GET", "/garmin/link/status"),
        (garmin_router.garmin_link_service, "get_link_status"),
        [
            garmin_schema.GarminLinkStatus(status=core_job_status.JobState.RUNNING),
            garmin_schema.GarminLinkStatus(status=core_job_status.JobState.RUNNING, mfa_required=True),
        ],
        [
            garmin_schema.GarminLinkStatus(status=core_job_status.JobState.SUCCEEDED),
            garmin_schema.GarminLinkStatus(
                status=core_job_status.JobState.FAILED, error_code=garmin_constants.LinkFailure.INTERNAL
            ),
        ],
        garmin_constants.LINK_POLL_SECONDS,
        id="garmin-link",
    ),
    pytest.param(
        ("GET", "/garmin/sync/gear"),
        (garmin_router.garmin_sync_service, "get_sync_status"),
        [
            garmin_schema.GarminSyncStatus(kind=garmin_constants.SyncKind.GEAR, status=_QUEUED),
            garmin_schema.GarminSyncStatus(kind=garmin_constants.SyncKind.GEAR, status=_SYNC_RUNNING),
        ],
        [
            garmin_schema.GarminSyncStatus(kind=garmin_constants.SyncKind.GEAR, status=_SYNC_DONE),
            garmin_schema.GarminSyncStatus(kind=garmin_constants.SyncKind.GEAR, status=_SYNC_FAILED),
        ],
        garmin_constants.SYNC_POLL_SECONDS,
        id="garmin-sync",
    ),
    pytest.param(
        ("GET", "/strava/sync/gear"),
        (strava_router.strava_sync_service, "get_sync_status"),
        [
            strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.GEAR, status=_QUEUED),
            strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.GEAR, status=_SYNC_RUNNING),
        ],
        [
            strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.GEAR, status=_SYNC_DONE),
            strava_schema.StravaSyncStatus(kind=strava_constants.SyncKind.GEAR, status=_SYNC_FAILED),
        ],
        strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR],
        id="strava-sync",
    ),
    pytest.param(
        ("GET", "/profile/export"),
        (profile_router.profile_export_job_service, "get_export_status"),
        [
            profile_schema.ProfileExportStatus(status=core_job_status.JobState.QUEUED),
            profile_schema.ProfileExportStatus(status=core_job_status.JobState.RUNNING),
        ],
        [
            profile_schema.ProfileExportStatus(status=core_job_status.JobState.SUCCEEDED),
            profile_schema.ProfileExportStatus(status=core_job_status.JobState.FAILED),
        ],
        profile_constants.EXPORT_POLL_SECONDS,
        id="profile-export",
    ),
    pytest.param(
        ("GET", "/profile/import"),
        (profile_router.profile_import_job_service, "get_import_status"),
        [
            profile_import_state_store.ProfileImportState(status=profile_constants.ImportStatus.QUEUED),
            profile_import_state_store.ProfileImportState(status=profile_constants.ImportStatus.RUNNING),
        ],
        [
            profile_import_state_store.ProfileImportState(status=profile_constants.ImportStatus.SUCCEEDED),
            profile_import_state_store.ProfileImportState(status=profile_constants.ImportStatus.FAILED),
        ],
        profile_constants.IMPORT_POLL_SECONDS,
        id="profile-import",
    ),
    pytest.param(
        ("GET", "/activities/bulk-edit"),
        (activity_router.activity_bulk_edit_job_service, "get_visibility_edit_status"),
        [
            activity_schema.ActivitiesBulkEditStatus(status=core_job_status.JobState.QUEUED),
            activity_schema.ActivitiesBulkEditStatus(status=core_job_status.JobState.RUNNING),
        ],
        [
            activity_schema.ActivitiesBulkEditStatus(status=core_job_status.JobState.SUCCEEDED),
            activity_schema.ActivitiesBulkEditStatus(status=core_job_status.JobState.FAILED),
        ],
        bulk_edit_constants.BULK_EDIT_POLL_SECONDS,
        id="bulk-edit",
    ),
    pytest.param(
        ("GET", "/users/12/deletion"),
        (users_router.users_deletion_job_service, "get_deletion_status"),
        [
            users_schema.UserDeletionStatus(status=core_job_status.JobState.QUEUED),
            users_schema.UserDeletionStatus(status=core_job_status.JobState.RUNNING),
        ],
        [
            users_schema.UserDeletionStatus(status=core_job_status.JobState.SUCCEEDED),
            users_schema.UserDeletionStatus(status=core_job_status.JobState.FAILED),
        ],
        users_constants.DELETION_POLL_SECONDS,
        id="user-deletion",
    ),
]


@pytest.mark.parametrize(("call", "service", "running", "finished", "retry_after"), _STATUS_ROUTES)
def test_a_status_read_asks_for_another_poll_only_while_the_work_runs(
    client, call, service, running, finished, retry_after
):
    method, path = call
    for state in running:
        with patch.object(*service, return_value=state):
            response = client.request(method, path)
        assert response.status_code == 200, response.text
        assert response.headers["Retry-After"] == str(retry_after)

    for state in finished:
        with patch.object(*service, return_value=state):
            response = client.request(method, path)
        assert response.status_code == 200, response.text
        assert "Retry-After" not in response.headers


def test_an_export_status_that_records_nothing_sends_no_retry_after(client):
    with patch.object(profile_router.profile_export_job_service, "get_export_status", return_value=None):
        response = client.get("/profile/export")

    assert response.json() is None
    assert "Retry-After" not in response.headers


@pytest.mark.parametrize(
    ("path", "service"),
    [
        ("/activities/bulk-edit", (activity_router.activity_bulk_edit_job_service, "get_visibility_edit_status")),
        ("/strava/sync/gear", (strava_router.strava_sync_service, "get_sync_status")),
        ("/garmin/sync/gear", (garmin_router.garmin_sync_service, "get_sync_status")),
        ("/garmin/link/status", (garmin_router.garmin_link_service, "get_link_status")),
        ("/users/7/deletion", (users_router.users_deletion_job_service, "get_deletion_status")),
        ("/profile/import", (profile_router.profile_import_job_service, "get_import_status")),
    ],
)
def test_a_status_read_that_records_nothing_is_200_null_with_no_retry_after(client, path, service):
    with patch.object(*service, return_value=None):
        response = client.get(path)

    assert response.status_code == 200, response.text
    assert response.json() is None
    assert "Retry-After" not in response.headers


class TestARefusedSecondRun:
    def test_a_bulk_import_conflict_names_the_running_job(self, client):
        running = core_exceptions.JobAlreadyRunningError(
            "A bulk import is already running",
            status_route=ingestion_constants.JOB_STATUS_ROUTE,
            status_params={"job_id": _JOB_ID},
            job_id=_JOB_ID,
        )
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

    def test_a_conflict_over_work_without_an_id_names_the_status_and_no_job(self, client):
        running = core_exceptions.JobAlreadyRunningError(
            "A Garmin Connect gear sync is already in progress",
            status_route="garminconnect_sync_status",
            status_params={"kind": "gear"},
        )
        with patch.object(garmin_router.garmin_sync_service, "request_gear_sync", side_effect=running):
            response = client.post("/garmin/gear")

        assert response.status_code == 409
        assert response.headers["Content-Location"] == "/garmin/sync/gear"
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
