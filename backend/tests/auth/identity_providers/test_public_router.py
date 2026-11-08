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
import core.pagination as core_pagination
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.public_router as public_router
import modules.auth.identity_providers.schema as idp_schema

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
    def test_returns_the_page_the_service_lists(self, client, service):
        provider = idp_schema.IdentityProviderPublicRead(id=1, name="Pocket ID", slug="pocket-id")
        service.get_enabled_identity_providers.return_value = idp_schema.IdentityProviderPublicPage.build(
            [provider], 1, 1, 25
        )

        response = client.get(PREFIX)

        assert response.status_code == 200
        body = response.json()
        assert [item["slug"] for item in body["items"]] == ["pocket-id"]
        assert (body["total"], body["next"]) == (1, None)
        assert service.get_enabled_identity_providers.call_args.args[0] == core_pagination.PageParams(1, 25)


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
        assert args[7] == core_config.settings.ALLOWED_REDIRECT_URIS

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
        client.cookies.set(idp_dependencies.BINDING_COOKIE_NAME, "binding-secret", path="/api/v1/public/idp/callback")

        response = self._callback(client)

        assert service.prepare_callback.call_args.args[:3] == ("pocket-id", "xyz", "binding-secret")
        assert f'{idp_dependencies.BINDING_COOKIE_NAME}=""' in response.headers["set-cookie"]
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


class TestBackchannelLogout:
    URL = f"{PREFIX}/pocket-id/backchannel-logout"

    @pytest.fixture
    def logout_service(self, client):
        logout_service = MagicMock()
        client.app.dependency_overrides[idp_dependencies.get_backchannel_logout_service] = lambda: logout_service
        return logout_service

    def test_a_handled_logout_answers_200_with_no_body_and_no_store(self, client, logout_service):
        response = client.post(self.URL, data={"logout_token": "a.b.c"})

        assert response.status_code == 200
        assert response.content == b""
        assert response.headers["cache-control"] == "no-store"
        assert logout_service.logout.call_args.args[:2] == ("pocket-id", "a.b.c")

    def test_a_refused_token_answers_400(self, client, logout_service):
        logout_service.logout.side_effect = core_exceptions.InvalidInputError("The logout token was refused")

        response = client.post(self.URL, data={"logout_token": "a.b.c"})

        assert response.status_code == 400
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_a_provider_without_back_channel_logout_answers_404(self, client, logout_service):
        logout_service.logout.side_effect = core_exceptions.NotFoundError("Identity provider not found")

        assert client.post(self.URL, data={"logout_token": "a.b.c"}).status_code == 404

    def test_an_unreachable_state_store_answers_503(self, client, logout_service):
        logout_service.logout.side_effect = core_exceptions.ServiceUnavailableError("unavailable")

        assert client.post(self.URL, data={"logout_token": "a.b.c"}).status_code == 503

    @pytest.mark.parametrize("data", [{}, {"logout_token": ""}, {"logout_token": "x" * 16_385}])
    def test_a_missing_or_oversized_token_is_a_validation_failure(self, client, logout_service, data):
        assert client.post(self.URL, data=data).status_code == 422
        logout_service.logout.assert_not_called()

    def test_a_nul_in_a_multipart_token_is_refused(self, client, logout_service):
        response = client.post(self.URL, files={"logout_token": (None, "a.b\x00.c")})

        assert response.status_code == 422
        logout_service.logout.assert_not_called()
