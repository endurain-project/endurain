"""The MFA routes read ``revoke_other_sessions`` from the body, default it to true and refuse a bare step-up body."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.account_security.mfa_router as mfa_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa_backup_codes.schema as mfa_backup_codes_schema

_WORKFLOW = "modules.auth.account_security.mfa_router.mfa_workflow_service"
_STEP_UP = {"step_up": {"current_password": "pw", "mfa_code": "123456"}}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(mfa_router.router, prefix="/profile/mfa")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_current_user_id] = lambda: 1
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: "sid"
    app.dependency_overrides[auth_dependencies.get_step_up_attempts] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.get_mfa_secret_store] = lambda: MagicMock()
    return TestClient(app)


def _post(client, path, body):
    with (
        patch(
            f"{_WORKFLOW}.enable_mfa",
            return_value=mfa_backup_codes_schema.MFABackupCodesRead(codes=["a"], created_at=datetime.now(UTC)),
        ) as e,
        patch(f"{_WORKFLOW}.disable_mfa") as d,
        patch(
            f"{_WORKFLOW}.generate_backup_codes",
            return_value=mfa_backup_codes_schema.MFABackupCodesRead(codes=["a"], created_at=datetime.now(UTC)),
        ) as g,
    ):
        response = client.post(f"/profile/mfa/{path}", json=body)
    return response, {"enable": e, "disable": d, "backup-codes": g}[path]


@pytest.mark.parametrize("path", ["disable", "backup-codes"])
@pytest.mark.parametrize(
    ("extra", "expected"),
    [({}, True), ({"revoke_other_sessions": True}, True), ({"revoke_other_sessions": False}, False)],
)
def test_the_step_up_routes_pass_the_choice_on(client, path, extra, expected):
    response, workflow = _post(client, path, {**_STEP_UP, **extra})

    assert response.status_code < 300
    assert workflow.call_args.kwargs["revoke_other_sessions"] is expected


@pytest.mark.parametrize(("extra", "expected"), [({}, True), ({"revoke_other_sessions": False}, False)])
def test_enable_carries_the_choice_in_its_request(client, extra, expected):
    response, workflow = _post(client, "enable", {"totp_code": "123456", **_STEP_UP, **extra})

    assert response.status_code == 200
    assert workflow.call_args.args[0].revoke_other_sessions is expected


@pytest.mark.parametrize("path", ["disable", "backup-codes"])
def test_an_unknown_key_is_refused(client, path):
    response, workflow = _post(client, path, {**_STEP_UP, "unexpected": 1})

    assert response.status_code == 422
    workflow.assert_not_called()


def test_enable_answers_with_the_backup_codes_body(client):
    response, _ = _post(client, "enable", {"totp_code": "123456", **_STEP_UP})

    assert response.status_code == 200
    assert set(response.json()) == {"codes", "created_at"}


def test_enable_refuses_the_old_mfa_code_field(client):
    response, workflow = _post(client, "enable", {"mfa_code": "123456", **_STEP_UP})

    assert response.status_code == 422
    workflow.assert_not_called()
