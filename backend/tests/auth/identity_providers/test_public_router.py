"""Tests for the public identity provider router: HTTP translation only.

The decisions behind each route are covered where they live, in ``test_service_sso_flow.py``.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_db
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.public_router as public_router
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.oauth_state.constants as oauth_state_constants

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


def _start(url, binding="binding"):
    return identity_provider_contracts.BrowserFlowStart(authorization_url=url, browser_binding=binding)


class TestListProviders:
    def test_returns_the_page_the_service_lists(self, client, service):
        provider = idp_schema.IdentityProviderPublicRead(id=uuid.uuid4(), name="Pocket ID", slug="pocket-id")
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

    def test_a_redirect_longer_than_the_stored_column_is_unprocessable(self, client, service):
        response = self._login(client, redirect="/" + "a" * oauth_state_constants.REDIRECT_MAX_LENGTH)

        assert response.status_code == 422
        service.begin_login.assert_not_called()

    def test_a_redirect_of_the_column_length_is_accepted(self, client, service):
        service.begin_login.return_value = _start("https://idp.example.com/authorize")

        response = self._login(client, redirect="/" + "a" * (oauth_state_constants.REDIRECT_MAX_LENGTH - 1))

        assert response.status_code == 307

    def test_redirects_to_the_authorization_url_the_service_built(self, client, service):
        service.begin_login.return_value = _start("https://provider.example/auth?state=abc")

        response = self._login(client, redirect="/dashboard")

        assert response.status_code == 307
        assert response.headers["location"] == "https://provider.example/auth?state=abc"

    def test_keeps_the_login_binding_in_a_cookie_for_the_callback(self, client, service):
        service.begin_login.return_value = _start("https://provider.example/auth", "login-secret")

        response = self._login(client)

        cookie = response.headers["set-cookie"]
        assert f"{idp_dependencies.BINDING_COOKIE_NAME}=login-secret" in cookie
        assert "Path=/;" in cookie or cookie.endswith("Path=/")
        assert "Domain" not in cookie
        assert f"Max-Age={oauth_state_constants.STATE_TTL_SECONDS}" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie

    def test_a_deployed_login_sets_a_host_locked_binding_cookie(self, client, service):
        service.begin_login.return_value = _start("https://provider.example/auth", "login-secret")

        with patch.object(idp_dependencies.core_config.settings, "ENVIRONMENT", "production"):
            response = self._login(client)

        cookie = response.headers["set-cookie"]
        assert cookie.startswith("__Host-endurain_idp_binding=login-secret")
        assert "Secure" in cookie
        assert "Path=/;" in cookie or cookie.endswith("Path=/")
        assert "Domain" not in cookie

    def test_the_binding_is_not_in_the_redirect_url(self, client, service):
        service.begin_login.return_value = _start("https://provider.example/auth", "login-secret")

        assert "login-secret" not in self._login(client).headers["location"]

    def test_hands_the_request_facts_to_the_service(self, client, service):
        service.begin_login.return_value = _start("https://provider.example/auth")

        self._login(client, redirect="/dashboard")

        args = service.begin_login.call_args.args
        assert args[0] == "pocket-id"
        assert args[1:4] == (CHALLENGE, "S256", "/dashboard")
        assert args[5] == core_config.settings.ALLOWED_REDIRECT_URIS

    def test_the_client_type_header_does_not_choose_the_client_type(self, client):
        real = authorization_service.AuthorizationService(MagicMock(), "https://app.example.com")
        client.app.dependency_overrides[idp_dependencies.get_authorization_service] = lambda: real
        with (
            patch.object(authorization_service.idp_crud, "get_identity_provider_by_slug", return_value=MagicMock()),
            patch.object(real, "create_login_oauth_state", return_value="state-id") as create_state,
            patch.object(real, "initiate_login", return_value="https://provider.example/auth"),
        ):
            response = client.get(
                f"{PREFIX}/login/pocket-id",
                params={"code_challenge": CHALLENGE, "code_challenge_method": "S256", "redirect": "/dashboard"},
                headers={"X-Client-Type": "mobile"},
                follow_redirects=False,
            )

        assert response.status_code == 307
        assert create_state.call_args.kwargs["client_type"] == "web"

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
        client.cookies.set(idp_dependencies.BINDING_COOKIE_NAME, "binding-secret", path="/")

        response = self._callback(client)

        assert service.prepare_callback.call_args.args[:3] == ("pocket-id", "xyz", "binding-secret")
        assert f'{idp_dependencies.BINDING_COOKIE_NAME}=""' in response.headers["set-cookie"]
        assert "Max-Age=0" in response.headers["set-cookie"]

    def test_the_iss_parameter_reaches_the_service(self, client, service):
        service.prepare_callback.return_value = (MagicMock(), MagicMock())
        service.complete_callback.return_value = "https://app.example.com/login?sso=success"

        client.get(
            f"{PREFIX}/callback/pocket-id?code=abc&state=xyz&iss=https://idp.example.com", follow_redirects=False
        )

        assert service.complete_callback.call_args.kwargs["iss"] == "https://idp.example.com"

    def test_the_code_and_state_are_required(self, client):
        response = client.get(f"{PREFIX}/callback/pocket-id", follow_redirects=False)

        assert response.status_code == 422


class TestLoginBindingRoundTrip:
    """The real login and callback routes and services, with a real cookie jar and an in-memory state store."""

    @pytest.fixture
    def make_client(self):
        states = {}
        idp = SimpleNamespace(id=uuid.uuid4(), slug="pocket-id", enabled=True)
        authorization = authorization_service.AuthorizationService(MagicMock(), "https://app.example.com")
        callback = callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), "https://app.example.com")

        def create_state(idp_id, **kwargs):
            states["state-id"] = SimpleNamespace(
                id="state-id",
                idp_id=idp_id,
                browser_binding_hash=kwargs["browser_binding_hash"],
                purpose="login",
                user_id=None,
                client_type="web",
            )
            return "state-id"

        def make():
            app = FastAPI()
            core_exceptions.register_exception_handlers(app)
            app.include_router(public_router.router, prefix=PREFIX)
            app.dependency_overrides[core_db.get_db] = lambda: MagicMock()
            app.dependency_overrides[idp_dependencies.get_authorization_service] = lambda: authorization
            app.dependency_overrides[idp_dependencies.get_callback_service] = lambda: callback
            app.dependency_overrides[credentials_integration.get_password_hasher] = lambda: MagicMock()
            # The cookie is Secure outside development, so a browser, and this jar, keeps it only over https.
            return TestClient(app, base_url="https://testserver")

        with (
            patch.object(authorization_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(authorization, "create_login_oauth_state", side_effect=create_state),
            patch.object(
                authorization,
                "initiate_login",
                side_effect=lambda _idp, _db, _redirect, oauth_state_id: (
                    f"https://provider.example/auth?state={oauth_state_id}"
                ),
            ),
            patch.object(callback, "get_unused_oauth_state", side_effect=lambda state, _db: states.get(state)),
            patch.object(callback, "claim_oauth_state", return_value=True),
            patch.object(callback, "complete_callback", return_value="https://app.example.com/login?sso=success"),
            patch.object(callback_service, "_record_login_refusal"),
        ):
            yield make, callback

    def _start(self, client):
        response = client.get(
            f"{PREFIX}/login/pocket-id",
            params={"code_challenge": CHALLENGE, "code_challenge_method": "S256"},
            follow_redirects=False,
        )
        assert response.status_code == 307
        return parse_qs(urlparse(response.headers["location"]).query)["state"][0]

    def test_the_login_cookie_reaches_the_callback_route_and_binds_the_browser(self, make_client):
        make, callback = make_client
        client = make()
        state = self._start(client)

        response = client.get(f"{PREFIX}/callback/pocket-id?state={state}&code=abc", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "https://app.example.com/login?sso=success"
        callback.complete_callback.assert_called_once()

    def test_a_browser_without_the_login_cookie_is_refused(self, make_client):
        make, callback = make_client
        state = self._start(make())

        response = make().get(f"{PREFIX}/callback/pocket-id?state={state}&code=abc", follow_redirects=False)

        assert response.status_code == 400
        callback.complete_callback.assert_not_called()


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
