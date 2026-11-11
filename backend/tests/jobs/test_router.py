"""Tests for the job routes: ``GET /jobs/{job_id}``, ``GET /jobs`` and the ``409`` that points at a running job."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.auth.contracts as auth_contracts
import modules.auth.dependencies as auth_dependencies
import modules.jobs.router as jobs_router
import modules.strava.constants as strava_constants
import modules.strava.sync_state_store as strava_sync_state_store

Status = core_job_status.JobState
_INGESTION_READ = "modules.activities.activity_ingestion.integration_service.read_job"


@pytest.fixture
def state():
    return MemoryState()


def _client(state, scopes=("account",), user_id=1) -> TestClient:
    app = FastAPI()
    app.include_router(jobs_router.router, prefix="/jobs")
    core_exceptions.register_exception_handlers(app)

    @app.post("/start")
    def start() -> None:
        strava_sync_state_store.StravaSyncStateStore(state).begin(
            user_id, strava_constants.SyncKind.GEAR, conflict="A Strava gear sync is already in progress"
        )

    app.dependency_overrides[auth_dependencies.get_principal] = lambda: auth_contracts.Principal(
        user_id=user_id,
        username="runner",
        email="runner@example.com",
        is_active=True,
        is_superuser=False,
        scopes=frozenset(scopes),
        credential=auth_contracts.AccessTokenCred(session_id="sid"),
    )
    app.dependency_overrides[core_dependencies.get_platform_state] = lambda: state
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    return TestClient(app)


def _gear(state, user_id=1):
    return strava_sync_state_store.StravaSyncStateStore(state).begin(
        user_id, strava_constants.SyncKind.GEAR, conflict="Busy"
    )


class TestReadJob:
    def test_a_running_job_is_read_with_its_kind_and_asks_to_be_polled(self, state):
        job = _gear(state)

        response = _client(state).get(f"/jobs/{job.id}")

        assert response.status_code == 200
        body = response.json()
        assert (body["id"], body["kind"], body["status"]) == (job.id, "strava_gear", "queued")
        assert response.headers["Retry-After"] == str(
            strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR]
        )

    def test_a_finished_job_is_not_polled_again(self, state):
        job = _gear(state)
        strava_sync_state_store.StravaSyncStateStore(state).set_status(
            1, strava_constants.SyncKind.GEAR, Status.SUCCEEDED
        )

        response = _client(state).get(f"/jobs/{job.id}")

        assert response.json()["status"] == "succeeded"
        assert response.json()["finished_at"] is not None
        assert "Retry-After" not in response.headers

    def test_a_job_read_without_the_scope_its_kind_needs_is_forbidden(self, state):
        job = _gear(state)

        assert _client(state, scopes=("activities:upload",)).get(f"/jobs/{job.id}").status_code == 403

    def test_another_users_job_and_an_unknown_id_are_not_found(self, state):
        job = _gear(state, user_id=2)

        with patch(_INGESTION_READ, return_value=None):
            assert _client(state).get(f"/jobs/{job.id}").status_code == 404
            assert _client(state).get("/jobs/missing").status_code == 404


class TestListJobs:
    def test_the_callers_jobs_are_listed(self, state):
        job = _gear(state)

        response = _client(state).get("/jobs", params={"kind": "strava_gear", "status": "queued"})

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [job.id]
        assert response.json()["next_cursor"] is None

    def test_an_unknown_kind_is_refused(self, state):
        assert _client(state).get("/jobs", params={"kind": "nope"}).status_code == 422


def test_a_refused_second_start_points_at_the_running_job(state):
    client = _client(state)
    assert client.post("/start").status_code == 200

    response = client.post("/start")

    assert response.status_code == 409
    job_id = response.json()["job_id"]
    assert response.headers["Content-Location"] == f"/jobs/{job_id}"
