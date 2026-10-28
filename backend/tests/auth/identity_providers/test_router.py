"""Tests for identity-provider admin routes."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.router as idp_router
import modules.auth.identity_providers.schema as idp_schema


def _client(service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(idp_router.router, prefix="/auth/identity_providers")
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[idp_dependencies.get_identity_provider_service] = lambda: service
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    return TestClient(app)


def _provider() -> idp_schema.IdentityProviderRead:
    now = datetime.now(UTC)
    return idp_schema.IdentityProviderRead(id=1, name="Google", slug="google", created_at=now, updated_at=now)


def test_list_identity_providers_delegates_to_service():
    service = MagicMock()
    service.list_identity_providers.return_value = [_provider()]

    response = _client(service).get("/auth/identity_providers", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "google"
    service.list_identity_providers.assert_called_once()


def test_list_templates_delegates_to_service():
    service = MagicMock()
    service.get_idp_templates.return_value = []

    response = _client(service).get("/auth/identity_providers/templates", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.json() == []


def test_create_identity_provider_delegates_to_service():
    service = MagicMock()
    service.create_identity_provider.return_value = _provider()

    response = _client(service).post(
        "/auth/identity_providers",
        json={"name": "Google", "slug": "google", "client_id": "client", "client_secret": "secret"},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 201
    service.create_identity_provider.assert_called_once()


def test_update_identity_provider_uses_positive_id_and_service():
    service = MagicMock()
    service.update_identity_provider.return_value = _provider()

    response = _client(service).put(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 200
    service.update_identity_provider.assert_called_once()


def test_update_rejects_nonpositive_id():
    service = MagicMock()

    response = _client(service).put(
        "/auth/identity_providers/0",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 422
    service.update_identity_provider.assert_not_called()


def test_delete_identity_provider_delegates_to_service():
    service = MagicMock()

    response = _client(service).delete("/auth/identity_providers/1", headers={"Authorization": "Bearer x"})

    assert response.status_code == 204
    service.delete_identity_provider.assert_called_once()
    assert service.delete_identity_provider.call_args.args[0] == 1
