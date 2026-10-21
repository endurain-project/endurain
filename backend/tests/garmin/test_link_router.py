"""Tests for the Garmin Connect link routes."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store

_BODY = {"username": "me@example.com", "password": "pw", "is_cn": False}


def _client(user_id: int = 1):
    import modules.auth.dependencies as auth_deps
    import modules.garmin.router as router

    state = MemoryState()
    link_states = link_state_store.GarminLinkStateStore(state=state)
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/garminconnect")
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
    app.dependency_overrides[link_state_store.get_garmin_link_state_store] = lambda: link_states
    app.dependency_overrides[mfa_code_store.get_garmin_mfa_code_store] = lambda: mfa_code_store.GarminMFACodeStore(
        state=state
    )
    return TestClient(app), link_states


@patch("modules.garmin.router.garmin_utils.start_garminconnect_link")
def test_link_returns_pending_at_once_and_starts_the_login(mock_start):
    client, link_states = _client()

    response = client.post("/garminconnect/link", json=_BODY)

    assert response.status_code == 202
    assert response.json() == {"status": "pending", "reason": None}
    assert link_states.get(1).status == link_state_store.LinkStatus.PENDING
    assert mock_start.call_args.args[:2] == (1, "me@example.com")


@patch("modules.garmin.router.garmin_utils.start_garminconnect_link")
def test_a_second_link_while_one_runs_is_a_conflict(mock_start):
    client, _ = _client()
    client.post("/garminconnect/link", json=_BODY)

    response = client.post("/garminconnect/link", json=_BODY)

    assert response.status_code == 409
    mock_start.assert_called_once()


@patch("modules.garmin.router.garmin_utils.start_garminconnect_link")
def test_a_failed_link_can_be_retried(mock_start):
    client, link_states = _client()
    client.post("/garminconnect/link", json=_BODY)
    link_states.set_status(1, link_state_store.LinkStatus.FAILED, link_state_store.LinkFailure.INCORRECT_MFA)

    assert client.post("/garminconnect/link", json=_BODY).status_code == 202


def test_status_without_an_attempt_is_not_found():
    client, _ = _client()

    assert client.get("/garminconnect/link/status").status_code == 404


def test_status_reports_the_prompt_and_the_outcome():
    client, link_states = _client()
    link_states.begin(1)

    link_states.set_status(1, link_state_store.LinkStatus.MFA_REQUIRED)
    assert client.get("/garminconnect/link/status").json()["status"] == "mfa_required"

    link_states.set_status(1, link_state_store.LinkStatus.FAILED, link_state_store.LinkFailure.INVALID_CREDENTIALS)
    assert client.get("/garminconnect/link/status").json() == {"status": "failed", "reason": "invalid_credentials"}


def test_status_is_scoped_to_the_caller():
    client, link_states = _client(user_id=2)
    link_states.begin(1)

    assert client.get("/garminconnect/link/status").status_code == 404
