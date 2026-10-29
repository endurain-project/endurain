"""Tests for identity-provider admin routes."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.router as idp_router
import modules.auth.identity_providers.schema as idp_schema


def _client() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.include_router(idp_router.router, prefix="/auth/identity_providers")
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    return TestClient(app)


@pytest.fixture
def service(monkeypatch) -> MagicMock:
    """Replace the provider service the routes call."""
    service = MagicMock()
    monkeypatch.setattr(idp_router, "idp_provider_service", service)
    return service


def _provider(version: int = 1) -> idp_schema.IdentityProviderRead:
    now = datetime.now(UTC)
    return idp_schema.IdentityProviderRead(
        id=1, name="Google", slug="google", created_at=now, updated_at=now, version=version
    )


def test_list_identity_providers_delegates_to_service(service):
    service.list_identity_providers.return_value = [_provider()]

    response = _client().get("/auth/identity_providers", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.json()[0]["slug"] == "google"
    assert response.json()[0]["version"] == 1
    service.list_identity_providers.assert_called_once()


def test_list_templates_delegates_to_service(service):
    service.get_idp_templates.return_value = []

    response = _client().get("/auth/identity_providers/templates", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.json() == []


def test_create_identity_provider_delegates_to_service(service):
    service.create_identity_provider.return_value = _provider()

    response = _client().post(
        "/auth/identity_providers",
        json={"name": "Google", "slug": "google", "client_id": "client", "client_secret": "secret"},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'
    service.create_identity_provider.assert_called_once()


def test_update_identity_provider_requires_if_match_and_returns_new_etag(service):
    service.update_identity_provider.return_value = _provider(version=2)

    response = _client().put(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x", "If-Match": '"1"'},
    )

    assert response.status_code == 200
    assert response.headers["etag"] == '"2"'
    service.update_identity_provider.assert_called_once()
    assert service.update_identity_provider.call_args.kwargs["if_match"] == '"1"'


def test_update_requires_if_match_before_calling_service(service):

    response = _client().put(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 428
    service.update_identity_provider.assert_not_called()


def test_update_rejects_if_match_wildcard_before_calling_service(service):

    response = _client().put(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x", "If-Match": "*"},
    )

    assert response.status_code == 400
    service.update_identity_provider.assert_not_called()


def test_update_returns_precondition_failed_for_a_stale_etag(service):
    service.update_identity_provider.side_effect = core_exceptions.PreconditionFailedError("stale")

    response = _client().put(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x", "If-Match": '"1"'},
    )

    assert response.status_code == 412
    service.update_identity_provider.assert_called_once()


def test_update_rejects_nonpositive_id(service):

    response = _client().put(
        "/auth/identity_providers/0",
        json={"name": "Google", "slug": "google"},
        headers={"Authorization": "Bearer x", "If-Match": '"1"'},
    )

    assert response.status_code == 422
    service.update_identity_provider.assert_not_called()


def test_delete_identity_provider_delegates_to_service(service):

    response = _client().delete("/auth/identity_providers/1", headers={"Authorization": "Bearer x", "If-Match": '"2"'})

    assert response.status_code == 204
    service.delete_identity_provider.assert_called_once()
    assert service.delete_identity_provider.call_args.args[0] == 1
    assert service.delete_identity_provider.call_args.kwargs == {"if_match": '"2"'}


def test_delete_without_if_match_is_428(service):

    response = _client().delete("/auth/identity_providers/1", headers={"Authorization": "Bearer x"})

    assert response.status_code == 428
    service.delete_identity_provider.assert_not_called()


def test_delete_returns_precondition_failed_for_a_stale_etag(service):
    service.delete_identity_provider.side_effect = core_exceptions.PreconditionFailedError("stale")

    response = _client().delete("/auth/identity_providers/1", headers={"Authorization": "Bearer x", "If-Match": '"1"'})

    assert response.status_code == 412
