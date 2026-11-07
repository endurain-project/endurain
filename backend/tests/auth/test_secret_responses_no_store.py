"""Responses that carry a one-time secret are not cacheable."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.auth.account_security.mfa_router as mfa_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.schema as mfa_schema
import modules.auth.mfa_backup_codes.schema as mfa_backup_codes_schema

_WORKFLOW = "modules.auth.account_security.mfa_router.mfa_workflow_service"


@pytest.fixture
def mfa_client() -> TestClient:
    app = FastAPI()
    app.include_router(mfa_router.router, prefix="/profile/mfa")
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: "sid"
    app.dependency_overrides[auth_dependencies.get_step_up_attempts] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.get_mfa_secret_store] = lambda: MagicMock()
    return TestClient(app)


def _assert_no_store(response) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_mfa_setup_is_no_store(mfa_client):
    read = mfa_schema.MFASetupRead(secret="S", qr_code="Q", app_name="Endurain")
    with patch(f"{_WORKFLOW}.setup_mfa", return_value=read):
        response = mfa_client.post("/profile/mfa/setup")

    assert response.status_code == 201
    _assert_no_store(response)


def test_mfa_enable_is_no_store(mfa_client):
    read = mfa_schema.MFAEnableRead(message="ok", backup_codes=["a"])
    with patch(f"{_WORKFLOW}.enable_mfa", return_value=read):
        response = mfa_client.post(
            "/profile/mfa/enable", json={"mfa_code": "123456", "step_up": {"current_password": "x"}}
        )

    assert response.status_code == 200, response.text
    _assert_no_store(response)


def test_mfa_backup_codes_is_no_store(mfa_client):
    from datetime import UTC, datetime

    read = mfa_backup_codes_schema.MFABackupCodesRead(codes=["a"], created_at=datetime.now(UTC))
    with patch(f"{_WORKFLOW}.generate_backup_codes", return_value=read):
        response = mfa_client.post("/profile/mfa/backup-codes", json={"step_up": {"current_password": "x"}})

    assert response.status_code == 201, response.text
    _assert_no_store(response)
