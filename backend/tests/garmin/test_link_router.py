"""Tests for the Garmin Connect link routes."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState

import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.dependencies as garmin_dependencies
import modules.garmin.link_state_store as link_state_store
import modules.garmin.mfa_code_store as mfa_code_store
import modules.garmin.schema as garmin_schema
import modules.garmin.sync_state_store as sync_state_store

_BODY = {"username": "me@example.com", "password": "pw", "is_cn": False}


def _client(user_id: int = 1):
    import modules.auth.dependencies as auth_deps
    import modules.garmin.router as router

    state = MemoryState()
    link_states = link_state_store.GarminLinkStateStore(state=state)
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/garmin")
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[garmin_dependencies.get_garmin_link_state_store] = lambda: link_states
    app.dependency_overrides[garmin_dependencies.get_garmin_mfa_code_store] = lambda: mfa_code_store.GarminMFACodeStore(
        state=state
    )
    app.dependency_overrides[garmin_dependencies.get_garmin_sync_state_store] = lambda: (
        sync_state_store.GarminSyncStateStore(state=state)
    )
    return TestClient(app), link_states


@pytest.fixture(autouse=True)
def users_today():
    with patch("modules.garmin.sync_service.users_integration.local_today", return_value=date(2026, 1, 31)):
        yield


@patch("modules.garmin.link_service._link_pool")
def test_link_returns_pending_at_once_and_starts_the_login(mock_start):
    client, link_states = _client()

    response = client.post("/garmin/link", json=_BODY)

    assert response.status_code == 202
    assert response.json() == {"status": "pending", "reason": None}
    assert link_states.get(1).status == garmin_constants.LinkStatus.PENDING
    assert mock_start.submit.call_args.args[1:3] == (1, "me@example.com")


@patch("modules.garmin.link_service._link_pool")
def test_a_second_link_while_one_runs_is_a_conflict(mock_start):
    client, _ = _client()
    client.post("/garmin/link", json=_BODY)

    response = client.post("/garmin/link", json=_BODY)

    assert response.status_code == 409
    mock_start.submit.assert_called_once()


@patch("modules.garmin.link_service._link_pool")
def test_a_failed_link_can_be_retried(mock_start):
    client, link_states = _client()
    client.post("/garmin/link", json=_BODY)
    link_states.set_status(1, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INCORRECT_MFA)

    assert client.post("/garmin/link", json=_BODY).status_code == 202


def test_status_without_an_attempt_is_not_found():
    client, _ = _client()

    assert client.get("/garmin/link/status").status_code == 404


def test_status_reports_the_prompt_and_the_outcome():
    client, link_states = _client()
    link_states.begin(1)

    link_states.set_status(1, garmin_constants.LinkStatus.MFA_REQUIRED)
    assert client.get("/garmin/link/status").json()["status"] == "mfa_required"

    link_states.set_status(1, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INVALID_CREDENTIALS)
    assert client.get("/garmin/link/status").json() == {"status": "failed", "reason": "invalid_credentials"}


def test_status_is_scoped_to_the_caller():
    client, link_states = _client(user_id=2)
    link_states.begin(1)

    assert client.get("/garmin/link/status").status_code == 404


def test_an_mfa_code_with_no_login_waiting_is_a_conflict():
    client, link_states = _client()
    link_states.begin(1)

    assert client.post("/garmin/mfa", json={"mfa_code": "123456"}).status_code == 409


def test_an_mfa_code_is_accepted_while_the_login_waits():
    client, link_states = _client()
    link_states.begin(1)
    link_states.set_status(1, garmin_constants.LinkStatus.MFA_REQUIRED)

    assert client.post("/garmin/mfa", json={"mfa_code": "123456"}).status_code == 204


def test_oversized_credentials_and_codes_are_rejected():
    client, _ = _client()

    assert client.post("/garmin/link", json={**_BODY, "password": "x" * 1000}).status_code == 422
    assert client.post("/garmin/mfa", json={"mfa_code": "1" * 100}).status_code == 422


def test_a_gear_sync_is_queued_not_run_on_the_request():
    client, _ = _client()
    with patch("modules.garmin.sync_service._queue") as queue:
        queue.return_value = garmin_schema.GarminSyncStatus(
            kind=garmin_constants.SyncKind.GEAR, status=garmin_constants.SyncStatus.QUEUED
        )
        response = client.post("/garmin/gear")

    assert response.status_code == 202
    assert response.json() == {"kind": "gear", "status": "queued"}
    queue.assert_called_once()


def test_a_second_gear_sync_while_one_is_pending_is_a_conflict():
    client, _ = _client()
    with (
        patch("modules.garmin.sync_service.core_config.settings", MagicMock(JOBS_ENABLED=False)),
        patch("modules.garmin.sync_service._sync_pool"),
    ):
        first = client.post("/garmin/gear")
        second = client.post("/garmin/gear")

    assert first.status_code == 202
    assert second.status_code == 409


def test_a_sync_status_is_reported_once_queued_and_not_found_before():
    client, _ = _client()
    assert client.get("/garmin/sync/health").status_code == 404

    with (
        patch("modules.garmin.sync_service.core_config.settings", MagicMock(JOBS_ENABLED=False)),
        patch("modules.garmin.sync_service._sync_pool"),
    ):
        client.post("/garmin/health", params={"start_date": "2026-01-01", "end_date": "2026-01-01"})

    assert client.get("/garmin/sync/health").json() == {"kind": "health", "status": "queued"}
    assert client.get("/garmin/sync/gear").status_code == 404


def test_a_non_numeric_mfa_code_is_rejected():
    client, _ = _client()

    assert client.post("/garmin/mfa", json={"mfa_code": "12 34!"}).status_code == 422


def test_unlinking_is_a_delete_on_the_link():
    client, _ = _client()
    with patch("modules.garmin.service.unlink_account") as unlink:
        response = client.delete("/garmin/link")

    assert response.status_code == 204
    assert response.content == b""
    unlink.assert_called_once()


def test_a_reversed_health_range_is_a_client_error():
    client, _ = _client()

    response = client.post("/garmin/health", params={"start_date": "2026-01-02", "end_date": "2026-01-01"})

    assert response.status_code == 400


def _route_scopes(path: str, method: str) -> set[str]:
    import modules.garmin.router as router

    route = next(r for r in router.router.routes if r.path == path and method in r.methods)
    return {scope for dep in route.dependant.dependencies for scope in dep.own_oauth_scopes or []}


def test_each_route_requires_the_scope_of_what_it_touches():
    assert _route_scopes("/link", "POST") == {"profile"}
    assert _route_scopes("/link", "DELETE") == {"profile"}
    assert _route_scopes("/mfa", "POST") == {"profile"}
    assert _route_scopes("/link/status", "GET") == {"profile"}
    assert _route_scopes("/sync/{kind}", "GET") == {"profile"}
    assert _route_scopes("/activities", "POST") == {"activities:write"}
    assert _route_scopes("/gear", "POST") == {"gears:write"}
    assert _route_scopes("/health", "POST") == {"health:write"}
