"""Tests for profile browser redirect router."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import auth.identity_service as auth_identity_service
import core.config as core_config
import core.database as core_database
import users.users_profile.browser_redirect_router as profile_browser_redirect_router


class TestLinkIdentityProvider:
    """Test suite for link_identity_provider endpoint."""

    endpoint = "/api/v1/profile/idp/1/link?link_token=test-token"

    def _make_app(self):
        app = FastAPI()
        app.include_router(
            profile_browser_redirect_router.router,
            prefix=core_config.ROOT_PATH + "/profile",
        )
        mock_db = MagicMock(spec=Session)
        mock_identity_service = MagicMock()
        app.dependency_overrides[core_database.get_db] = lambda: mock_db
        app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
        return app, mock_identity_service

    def test_successful_redirect(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_idp = MagicMock(spec=["enabled", "name"])
        mock_idp.enabled = True
        mock_idp.name = "TestIdP"

        mock_identity_service.validate_and_claim_browser_link_token.return_value = 1
        with (
            patch(
                "users.users_profile.browser_redirect_router.idp_service.get_identity_provider", return_value=mock_idp
            ),
            patch(
                "users.users_profile.browser_redirect_router.oauth_state_utils.create_state_id_and_nonce",
                return_value=("state-id", "nonce"),
            ),
            patch("users.users_profile.browser_redirect_router.idp_service.create_link_oauth_state"),
            patch(
                "users.users_profile.browser_redirect_router.idp_service.idp_service.initiate_link",
                new_callable=AsyncMock,
                return_value="https://idp.example.com/auth",
            ),
        ):
            response = client.get(self.endpoint, follow_redirects=False)

        assert response.status_code == 307, f"Expected 307, got {response.status_code}: {response.text}"
        assert response.headers["location"] == "https://idp.example.com/auth"

    def test_redirect_stored_on_oauth_state(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_idp = MagicMock(spec=["enabled", "name"])
        mock_idp.enabled = True
        mock_idp.name = "TestIdP"

        mock_identity_service.validate_and_claim_browser_link_token.return_value = 1
        with (
            patch(
                "users.users_profile.browser_redirect_router.idp_service.get_identity_provider", return_value=mock_idp
            ),
            patch(
                "users.users_profile.browser_redirect_router.oauth_state_utils.create_state_id_and_nonce",
                return_value=("state-id", "nonce"),
            ),
            patch(
                "users.users_profile.browser_redirect_router.idp_service.create_link_oauth_state"
            ) as mock_create_state,
            patch(
                "users.users_profile.browser_redirect_router.idp_service.idp_service.initiate_link",
                new_callable=AsyncMock,
                return_value="https://idp.example.com/auth",
            ),
        ):
            response = client.get(
                self.endpoint + "&redirect=/settings/security",
                follow_redirects=False,
            )

        assert response.status_code == 307
        kwargs = mock_create_state.call_args.kwargs
        assert kwargs["redirect_path"] == "/settings/security"
        assert kwargs["client_type"] == "web"

    def test_invalid_redirect_rejected_before_token_claim(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        response = client.get(
            self.endpoint + "&redirect=https://evil.example.com",
            follow_redirects=False,
        )

        assert response.status_code == 400
        # The one-time link token must not be consumed when the redirect is invalid.
        mock_identity_service.validate_and_claim_browser_link_token.assert_not_called()

    def test_invalid_token(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_identity_service.validate_and_claim_browser_link_token.side_effect = HTTPException(
            status_code=401, detail="Invalid or expired link token"
        )
        response = client.get(self.endpoint)

        assert response.status_code == 401

    def test_idp_mismatch(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_identity_service.validate_and_claim_browser_link_token.side_effect = HTTPException(
            status_code=401, detail="Invalid link token for this identity provider"
        )
        response = client.get(self.endpoint)

        assert response.status_code == 401

    def test_idp_not_found(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_identity_service.validate_and_claim_browser_link_token.return_value = 1
        with (
            patch("users.users_profile.browser_redirect_router.idp_service.get_identity_provider", return_value=None),
        ):
            response = client.get(self.endpoint)

        assert response.status_code == 404

    def test_idp_disabled(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_idp = MagicMock()
        mock_idp.enabled = False

        mock_identity_service.validate_and_claim_browser_link_token.return_value = 1
        with (
            patch(
                "users.users_profile.browser_redirect_router.idp_service.get_identity_provider", return_value=mock_idp
            ),
        ):
            response = client.get(self.endpoint)

        assert response.status_code == 404

    def test_already_linked(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_identity_service.validate_and_claim_browser_link_token.side_effect = HTTPException(
            status_code=409, detail="Identity provider TestIdP is already linked to your account"
        )
        response = client.get(self.endpoint)

        assert response.status_code == 409

    def test_token_replay(self):
        app, mock_identity_service = self._make_app()
        client = TestClient(app)

        mock_identity_service.validate_and_claim_browser_link_token.side_effect = HTTPException(
            status_code=400, detail="Invalid or expired link token"
        )
        response = client.get(self.endpoint)

        assert response.status_code == 400
