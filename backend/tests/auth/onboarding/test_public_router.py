"""Tests for the public first-run onboarding endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.onboarding.public_router as onboarding_public_router
import modules.auth.onboarding.schema as onboarding_schema
import modules.users.users.schema as users_schema

_SERVICE = "modules.auth.onboarding.public_router.onboarding_service"
_BODY = {
    "token": "setup-token",
    "name": "Owner",
    "username": "owner",
    "email": "owner@example.com",
    "password": "SecurePass1!",
}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(onboarding_public_router.router, prefix="/public/onboarding")
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock(spec=Session)
    app.dependency_overrides[core_dependencies.get_platform_state] = lambda: MemoryState()
    core_exceptions.register_exception_handlers(app)
    return TestClient(app)


def _admin() -> users_schema.UsersRead:
    return users_schema.UsersRead(
        id=1, name="Owner", username="owner", email="owner@example.com", active=True, access_type="admin"
    )


class TestStatus:
    @pytest.mark.parametrize("required", [True, False])
    def test_reports_the_status(self, client, required):
        with patch(f"{_SERVICE}.get_onboarding_status") as status_call:
            status_call.return_value = onboarding_schema.OnboardingStatusRead(onboarding_required=required)

            response = client.get("/public/onboarding")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"onboarding_required": required}


class TestComplete:
    def test_creates_the_administrator(self, client):
        with patch(f"{_SERVICE}.complete_onboarding", return_value=_admin()) as complete:
            response = client.post("/public/onboarding", json=_BODY)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["access_type"] == "admin"
        sent = complete.call_args.args[0]
        assert sent.token == "setup-token" and sent.username == "owner"

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (core_exceptions.ConflictError("An account already exists"), status.HTTP_409_CONFLICT),
            (core_exceptions.InvalidInputError("Invalid or expired setup token"), status.HTTP_400_BAD_REQUEST),
            (credentials_contracts.PasswordPolicyError("too short"), status.HTTP_422_UNPROCESSABLE_CONTENT),
            (core_exceptions.ServiceUnavailableError(), status.HTTP_503_SERVICE_UNAVAILABLE),
        ],
    )
    def test_maps_each_refusal_to_its_status(self, client, error, expected):
        with patch(f"{_SERVICE}.complete_onboarding", side_effect=error):
            response = client.post("/public/onboarding", json=_BODY)

        assert response.status_code == expected

    @pytest.mark.parametrize("field", ["access_type", "active", "email_verified", "pending_admin_approval"])
    def test_rejects_a_field_that_would_choose_the_role_or_state(self, client, field):
        with patch(f"{_SERVICE}.complete_onboarding") as complete:
            response = client.post("/public/onboarding", json={**_BODY, field: "admin"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        complete.assert_not_called()

    @pytest.mark.parametrize("missing", list(_BODY))
    def test_requires_every_field(self, client, missing):
        body = {key: value for key, value in _BODY.items() if key != missing}

        response = client.post("/public/onboarding", json=body)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
