"""Tests for profile browser redirect router."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_database
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.users.users_profile.browser_redirect_router as profile_browser_redirect_router
import modules.users.users_profile.service as profile_service

_START = identity_provider_contracts.BrowserFlowStart(
    authorization_url="https://idp.example.com/auth", browser_binding="binding-secret"
)


class TestLinkIdentityProvider:
    """Test suite for link_identity_provider endpoint."""

    endpoint = "/api/v1/profile/identity-providers/1/link?link_token=test-token"

    def _make_app(self):
        app = FastAPI()
        app.include_router(
            profile_browser_redirect_router.router,
            prefix=core_config.ROOT_PATH + "/profile",
        )
        app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
        return app

    def test_redirects_to_the_authorization_url(self):
        app = self._make_app()
        with patch.object(profile_service, "start_identity_provider_link", return_value=_START) as start_link:
            response = TestClient(app).get(self.endpoint, follow_redirects=False)
        start_link.assert_called_once()

        assert response.status_code == 307
        assert response.headers["location"] == "https://idp.example.com/auth"
        assert "no-store" in response.headers["cache-control"]

    def test_binds_the_link_to_this_browser_with_a_callback_scoped_cookie(self):
        app = self._make_app()
        with patch.object(profile_service, "start_identity_provider_link", return_value=_START):
            response = TestClient(app).get(self.endpoint, follow_redirects=False)

        cookie = response.headers["set-cookie"]
        assert cookie.startswith("endurain_idp_binding=binding-secret;")
        # Lax, not Strict: the callback is a top-level navigation back from the provider's site.
        for attribute in ("HttpOnly", "Max-Age=600", "Path=/api/v1/public/idp/callback", "SameSite=lax"):
            assert attribute in cookie

    def test_passes_the_token_provider_and_return_path_through(self):
        app = self._make_app()
        with patch.object(profile_service, "start_identity_provider_link", return_value=_START) as start_link:
            TestClient(app).get(self.endpoint + "&redirect=/settings/security", follow_redirects=False)

        args = start_link.call_args.args
        assert args[:3] == ("test-token", 1, "/settings/security")

    def test_an_auth_refusal_is_returned_as_is(self):
        app = self._make_app()
        with patch.object(
            profile_service,
            "start_identity_provider_link",
            side_effect=HTTPException(status_code=401, detail="Invalid or expired link token"),
        ):
            assert TestClient(app).get(self.endpoint).status_code == 401

    def test_the_provider_id_must_be_positive(self):
        app = self._make_app()

        response = TestClient(app).get("/api/v1/profile/identity-providers/0/link?link_token=test-token")

        assert response.status_code == 422
