"""Tests for the public identity provider router: HTTP translation only.

The decisions behind each route are covered where they live, in ``test_service_sso_flow.py``.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_db
import core.exceptions as core_exceptions
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.public_router as public_router

PREFIX = "/api/v1/public/idp"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def client(service, monkeypatch):
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(public_router.router, prefix=PREFIX)
    app.dependency_overrides[core_db.get_db] = lambda: MagicMock()
    app.dependency_overrides[idp_dependencies.get_authorization_service] = lambda: service
    app.dependency_overrides[idp_dependencies.get_callback_service] = lambda: service
    monkeypatch.setattr(public_router, "idp_provider_service", service)
    app.dependency_overrides[credentials_integration.get_password_hasher] = lambda: MagicMock()
    return TestClient(app)


class TestListProviders:
    def test_returns_what_the_service_lists(self, client, service):
        service.get_enabled_identity_providers.return_value = []

        response = client.get(PREFIX)

        assert response.status_code == 200
        assert response.json() == []


class TestInitiateLogin:
    def _login(self, client, **overrides):
        params = {"code_challenge": CHALLENGE, "code_challenge_method": "S256", **overrides}
        return client.get(f"{PREFIX}/login/pocket-id", params=params, follow_redirects=False)

    def test_redirects_to_the_authorization_url_the_service_built(self, client, service):
        service.begin_login.return_value = "https://provider.example/auth?state=abc"

        response = self._login(client, redirect="/dashboard")

        assert response.status_code == 307
        assert response.headers["location"] == "https://provider.example/auth?state=abc"

    def test_hands_the_request_facts_to_the_service(self, client, service):
        service.begin_login.return_value = "https://provider.example/auth"

        self._login(client, redirect="/dashboard")

        args = service.begin_login.call_args.args
        assert args[0] == "pocket-id"
        assert args[1:4] == (CHALLENGE, "S256", "/dashboard")
        assert args[6] == core_config.settings.ALLOWED_REDIRECT_SCHEMES

    def test_a_refusal_is_a_problem_document(self, client, service):
        service.begin_login.side_effect = core_exceptions.NotFoundError("Identity provider not found or disabled")

        response = self._login(client)

        assert response.status_code == 404
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_pkce_parameters_are_required(self, client):
        response = client.get(f"{PREFIX}/login/pocket-id", follow_redirects=False)

        assert response.status_code == 422


class TestHandleCallback:
    def _callback(self, client):
        return client.get(f"{PREFIX}/callback/pocket-id?code=abc&state=xyz", follow_redirects=False)

    def test_redirects_to_wherever_the_service_says(self, client, service):
        service.prepare_callback.return_value = (MagicMock(), MagicMock())
        service.complete_callback.return_value = "https://app.example.com/login?sso=success&session_id=s"

        response = self._callback(client)

        assert response.status_code == 307
        assert response.headers["location"] == "https://app.example.com/login?sso=success&session_id=s"

    def test_a_rejected_state_never_reaches_the_provider_exchange(self, client, service):
        service.prepare_callback.side_effect = core_exceptions.InvalidInputError("Invalid or expired OAuth state")

        response = self._callback(client)

        assert response.status_code == 400
        service.complete_callback.assert_not_called()

    def test_the_browser_binding_reaches_the_state_check_and_is_cleared(self, client, service):
        service.prepare_callback.return_value = (MagicMock(), MagicMock())
        service.complete_callback.return_value = "https://app.example.com/settings/security?idp_link=success"
        client.cookies.set("endurain_idp_binding", "binding-secret", path="/api/v1/public/idp/callback")

        response = self._callback(client)

        assert service.prepare_callback.call_args.args[:3] == ("pocket-id", "xyz", "binding-secret")
        assert 'endurain_idp_binding=""' in response.headers["set-cookie"]
        assert "Max-Age=0" in response.headers["set-cookie"]

    def test_the_code_and_state_are_required(self, client):
        response = client.get(f"{PREFIX}/callback/pocket-id", follow_redirects=False)

        assert response.status_code == 422


class TestReadIcon:
    @pytest.fixture
    def icon_service(self, monkeypatch):
        icon_service = MagicMock()
        monkeypatch.setattr(public_router, "idp_icon_service", icon_service)
        return icon_service

    def test_serves_the_stored_image_with_its_entity_tag(self, client, icon_service):
        icon_service.get_public_icon.return_value = (7, 4)
        icon_service.read_icon.return_value = (b"\x89PNG", "image/png")

        response = client.get(f"{PREFIX}/tinyauth/icon")

        assert response.status_code == 200
        assert response.content == b"\x89PNG"
        assert response.headers["content-type"] == "image/png"
        assert response.headers["etag"] == '"4"'
        assert "no-cache" in response.headers["cache-control"]

    def test_a_matching_etag_is_a_304_without_reading_storage(self, client, icon_service):
        icon_service.get_public_icon.return_value = (7, 4)

        response = client.get(f"{PREFIX}/tinyauth/icon", headers={"If-None-Match": '"4"'})

        assert response.status_code == 304
        icon_service.read_icon.assert_not_called()

    def test_no_icon_to_serve_is_404(self, client, icon_service):
        icon_service.get_public_icon.return_value = None

        assert client.get(f"{PREFIX}/tinyauth/icon").status_code == 404

    def test_a_missing_blob_is_404(self, client, icon_service):
        icon_service.get_public_icon.return_value = (7, 4)
        icon_service.read_icon.return_value = None

        assert client.get(f"{PREFIX}/tinyauth/icon").status_code == 404
