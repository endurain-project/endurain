"""Tests for identity-provider admin routes."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.router as idp_router
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.schema as auth_schema

OIDC = MagicMock()
VERIFIER = MagicMock()
STEP_UP = {"current_password": "admin-password"}


def _client() -> TestClient:
    app = FastAPI()
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.include_router(idp_router.router, prefix="/auth/identity_providers")
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[core_dependencies.get_storage] = lambda: MagicMock()
    app.dependency_overrides[idp_dependencies.get_oidc_client_service] = lambda: OIDC
    app.dependency_overrides[auth_dependencies.get_step_up_verifier] = lambda: VERIFIER
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


def test_list_identity_providers_returns_the_page_for_the_requested_window(service):
    service.list_identity_providers.return_value = idp_schema.IdentityProviderPage.build([_provider()], 3, 2, 1)

    response = _client().get(
        "/auth/identity_providers",
        params={"page_number": 2, "num_records": 1},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["slug"] == "google"
    assert body["items"][0]["version"] == 1
    assert (body["total"], body["page"], body["next"]) == (3, 2, 3)
    assert service.list_identity_providers.call_args.args[0] == core_pagination.PageParams(2, 1)


def test_list_templates_delegates_to_service(service):
    service.get_idp_templates.return_value = []

    response = _client().get("/auth/identity_providers/templates", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.json() == []


def test_create_identity_provider_delegates_to_service(service):
    service.create_identity_provider.return_value = _provider()

    response = _client().post(
        "/auth/identity_providers",
        json={"name": "Google", "slug": "google", "client_id": "client", "client_secret": "secret", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'
    assert response.headers["location"] == "/auth/identity_providers/1"
    service.create_identity_provider.assert_called_once()


def test_read_identity_provider_returns_it_with_its_etag(service):
    service.get_identity_provider.return_value = _provider(version=3)

    response = _client().get("/auth/identity_providers/1", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.headers["etag"] == '"3"'
    assert "client_secret" not in response.json()
    assert service.get_identity_provider.call_args.args[0] == 1


def test_read_of_a_missing_identity_provider_is_404(service):
    service.get_identity_provider.side_effect = core_exceptions.NotFoundError("Identity provider not found")

    response = _client().get("/auth/identity_providers/99", headers={"Authorization": "Bearer x"})

    assert response.status_code == 404


def test_update_identity_provider_requires_if_match_and_returns_new_etag(service):
    service.update_identity_provider.return_value = _provider(version=2)

    response = _client().patch(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x", "If-Match": '"1"'},
    )

    assert response.status_code == 200
    assert response.headers["etag"] == '"2"'
    service.update_identity_provider.assert_called_once()
    assert service.update_identity_provider.call_args.args[4] is OIDC
    assert service.update_identity_provider.call_args.kwargs["if_match"] == '"1"'


def test_create_returns_400_for_a_refused_url(service):
    service.create_identity_provider.side_effect = core_exceptions.InvalidInputError("issuer_url: URL must use https")

    response = _client().post(
        "/auth/identity_providers",
        json={"name": "Google", "slug": "google", "client_id": "client", "client_secret": "secret", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 400


def test_update_requires_if_match_before_calling_service(service):

    response = _client().patch(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 428
    service.update_identity_provider.assert_not_called()


def test_update_rejects_if_match_wildcard_before_calling_service(service):

    response = _client().patch(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x", "If-Match": "*"},
    )

    assert response.status_code == 400
    service.update_identity_provider.assert_not_called()


def test_update_returns_precondition_failed_for_a_stale_etag(service):
    service.update_identity_provider.side_effect = core_exceptions.PreconditionFailedError("stale")

    response = _client().patch(
        "/auth/identity_providers/1",
        json={"name": "Google", "slug": "google", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x", "If-Match": '"1"'},
    )

    assert response.status_code == 412
    service.update_identity_provider.assert_called_once()


def test_update_rejects_nonpositive_id(service):

    response = _client().patch(
        "/auth/identity_providers/0",
        json={"name": "Google", "slug": "google", "step_up": STEP_UP},
        headers={"Authorization": "Bearer x", "If-Match": '"1"'},
    )

    assert response.status_code == 422
    service.update_identity_provider.assert_not_called()


def _delete(path: str = "/auth/identity_providers/1/delete", **kwargs):
    headers = {"Authorization": "Bearer x", **kwargs.pop("headers", {})}
    return _client().post(path, headers=headers, **kwargs)


def test_delete_identity_provider_delegates_to_service(service):
    response = _delete(json={"step_up": STEP_UP}, headers={"If-Match": '"2"'})

    assert response.status_code == 204
    service.delete_identity_provider.assert_called_once()
    args = service.delete_identity_provider.call_args.args
    assert args[0] == 1
    assert args[1] == auth_schema.StepUpVerification(current_password="admin-password")
    assert args[2] is VERIFIER
    assert args[4] is OIDC
    assert service.delete_identity_provider.call_args.kwargs == {"if_match": '"2"'}


def test_delete_without_a_step_up_is_422_and_never_reaches_the_service(service):
    response = _delete(json={}, headers={"If-Match": '"2"'})

    assert response.status_code == 422
    service.delete_identity_provider.assert_not_called()


def test_delete_with_a_refused_step_up_is_403(service):
    service.delete_identity_provider.side_effect = core_exceptions.StepUpFailedError()

    response = _delete(json={"step_up": STEP_UP}, headers={"If-Match": '"2"'})

    assert response.status_code == 403


def test_the_old_delete_route_is_gone(service):
    response = _client().delete("/auth/identity_providers/1", headers={"Authorization": "Bearer x", "If-Match": '"2"'})

    assert response.status_code == 405
    service.delete_identity_provider.assert_not_called()


def test_delete_without_if_match_is_428(service):
    response = _delete(json={"step_up": STEP_UP})

    assert response.status_code == 428
    service.delete_identity_provider.assert_not_called()


def test_delete_returns_precondition_failed_for_a_stale_etag(service):
    service.delete_identity_provider.side_effect = core_exceptions.PreconditionFailedError("stale")

    response = _delete(json={"step_up": STEP_UP}, headers={"If-Match": '"1"'})

    assert response.status_code == 412


@pytest.mark.parametrize(("replaced", "status_code"), [(False, 201), (True, 200)])
def test_putting_an_icon_answers_201_for_a_new_one_and_200_for_a_replacement(monkeypatch, replaced, status_code):
    icon_service = MagicMock()
    icon_service.upload_icon.return_value = (5, replaced)
    monkeypatch.setattr(idp_router, "idp_icon_service", icon_service)

    response = _client().put(
        "/auth/identity_providers/1/icon",
        files={"file": ("icon.png", b"ignored", "image/png")},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == status_code
    assert response.json() == {"version": 5}


def test_upload_icon_hands_the_service_a_reader_for_the_upload(monkeypatch):
    icon_service = MagicMock()
    icon_service.upload_icon.return_value = (5, False)
    monkeypatch.setattr(idp_router, "idp_icon_service", icon_service)

    response = _client().put(
        "/auth/identity_providers/1/icon",
        files={"file": ("icon.png", b"ignored", "image/png")},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 201
    assert response.json() == {"version": 5}
    idp_id, read_data = icon_service.upload_icon.call_args.args[:2]
    assert idp_id == 1
    assert callable(read_data)


def test_upload_icon_rejects_nonpositive_id(monkeypatch):
    icon_service = MagicMock()
    monkeypatch.setattr(idp_router, "idp_icon_service", icon_service)

    response = _client().put(
        "/auth/identity_providers/0/icon",
        files={"file": ("icon.png", b"x", "image/png")},
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 422
    icon_service.upload_icon.assert_not_called()


def test_delete_icon_delegates_to_the_service(monkeypatch):
    icon_service = MagicMock()
    monkeypatch.setattr(idp_router, "idp_icon_service", icon_service)

    response = _client().delete("/auth/identity_providers/1/icon", headers={"Authorization": "Bearer x"})

    assert response.status_code == 204
    assert icon_service.delete_icon.call_args.args[0] == 1


class TestStepUp:
    """Creating and editing a provider needs the administrator's step-up, which is not a provider field."""

    def test_create_without_a_step_up_is_422_and_never_reaches_the_service(self, service):
        response = _client().post(
            "/auth/identity_providers",
            json={"name": "Google", "slug": "google", "client_id": "client", "client_secret": "secret"},
            headers={"Authorization": "Bearer x"},
        )

        assert response.status_code == 422
        service.create_identity_provider.assert_not_called()

    def test_create_hands_the_service_the_provider_the_step_up_and_the_verifier(self, service):
        service.create_identity_provider.return_value = _provider()

        _client().post(
            "/auth/identity_providers",
            json={
                "name": "Google",
                "slug": "google",
                "client_id": "client",
                "client_secret": "secret",
                "step_up": STEP_UP,
            },
            headers={"Authorization": "Bearer x"},
        )

        data, step_up, verifier = service.create_identity_provider.call_args.args[:3]
        assert type(data) is idp_schema.IdentityProviderCreate
        assert "step_up" not in data.model_dump()
        assert step_up == auth_schema.StepUpVerification(current_password="admin-password")
        assert verifier is VERIFIER

    def test_a_refused_create_step_up_is_403(self, service):
        service.create_identity_provider.side_effect = core_exceptions.StepUpFailedError()

        response = _client().post(
            "/auth/identity_providers",
            json={
                "name": "Google",
                "slug": "google",
                "client_id": "client",
                "client_secret": "secret",
                "step_up": STEP_UP,
            },
            headers={"Authorization": "Bearer x"},
        )

        assert response.status_code == 403

    def test_update_without_a_step_up_is_422_and_never_reaches_the_service(self, service):
        response = _client().patch(
            "/auth/identity_providers/1",
            json={"name": "Google", "slug": "google"},
            headers={"Authorization": "Bearer x", "If-Match": '"1"'},
        )

        assert response.status_code == 422
        service.update_identity_provider.assert_not_called()

    def test_update_hands_the_service_only_the_fields_sent_and_the_step_up(self, service):
        service.update_identity_provider.return_value = _provider(version=2)

        _client().patch(
            "/auth/identity_providers/1",
            json={"name": "Renamed", "slug": "google", "step_up": STEP_UP},
            headers={"Authorization": "Bearer x", "If-Match": '"1"'},
        )

        args = service.update_identity_provider.call_args.args
        assert type(args[1]) is idp_schema.IdentityProviderUpdate
        assert args[1].model_dump(exclude_unset=True) == {"name": "Renamed", "slug": "google"}
        assert args[2] == auth_schema.StepUpVerification(current_password="admin-password")
        assert args[3] is VERIFIER
        assert args[4] is OIDC
        assert service.update_identity_provider.call_args.kwargs["if_match"] == '"1"'

    def test_a_refused_update_step_up_is_403(self, service):
        service.update_identity_provider.side_effect = core_exceptions.StepUpFailedError()

        response = _client().patch(
            "/auth/identity_providers/1",
            json={"name": "Google", "slug": "google", "step_up": STEP_UP},
            headers={"Authorization": "Bearer x", "If-Match": '"1"'},
        )

        assert response.status_code == 403
