"""A malformed session or API key id in a path answers 422 before any service runs."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.account_security.admin_api_keys_router as admin_api_keys_router
import modules.auth.account_security.api_keys_router as api_keys_router
import modules.auth.account_security.sessions_router as sessions_router
import modules.auth.dependencies as auth_dependencies

_USER_ID = uuid.UUID(int=7)
_SID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
_BODY = {"step_up": {"current_password": "pw"}}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(sessions_router.router, prefix="/profile/sessions")
    app.include_router(api_keys_router.router, prefix="/profile/api-keys")
    app.include_router(admin_api_keys_router.router, prefix="/users")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_current_user_id] = lambda: _USER_ID
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: _SID
    app.dependency_overrides[auth_dependencies.get_step_up_attempts] = lambda: MagicMock()
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("delete", "/profile/sessions/not-a-uuid"),
        ("post", "/profile/api-keys/not-a-uuid/revoke"),
        ("delete", "/profile/api-keys/not-a-uuid"),
        ("post", f"/users/{_USER_ID}/api-keys/not-a-uuid/revoke"),
    ],
)
def test_a_malformed_id_is_422(client, method, path):
    response = getattr(client, method)(path, **({"json": _BODY} if method == "post" else {}))

    assert response.status_code == 422
