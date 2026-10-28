"""Tests for the public identity provider router."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.public_router as public_router

public_router.idp_crud = idp_crud
public_router.idp_service = MagicMock(idp_service=MagicMock())
_test_service = public_router.idp_service.idp_service
_test_service.get_identity_provider_by_slug.side_effect = lambda slug, db: idp_crud.get_identity_provider_by_slug(
    slug, db
)


def _build_app() -> TestClient:
    app = FastAPI()
    app.include_router(public_router.router, prefix="/api/v1/public/idp")
    app.dependency_overrides[idp_dependencies.get_identity_provider_service] = lambda: _test_service
    return TestClient(app)


class TestInitiateLogin:
    """Test suite for initiate_login endpoint behavior."""

    @patch("modules.auth.identity_providers.public_router.oauth_state_crud.create_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.initiate_login")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    @patch("modules.auth.identity_providers.public_router.idp_utils.validate_redirect_url")
    @patch("modules.auth.identity_providers.public_router.auth_computation.validate_pkce_challenge")
    def test_custom_scheme_redirect_forces_mobile_client_type(
        self,
        mock_validate_pkce,
        mock_validate_redirect,
        mock_get_idp,
        mock_initiate_login,
        mock_create_state,
    ):
        """Test custom-scheme redirects keep the OAuth state in mobile mode."""
        client = _build_app()

        mock_idp = MagicMock(spec=idp_models.IdentityProvider)
        mock_idp.id = 1
        mock_idp.slug = "pocket-id"
        mock_get_idp.return_value = mock_idp
        mock_initiate_login.return_value = "https://provider.example/auth?state=abc"

        response = client.get(
            "/api/v1/public/idp/login/pocket-id",
            params={
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "redirect": "gadgetbridge://endurain/oauth/callback",
            },
            headers={"X-Client-Type": "web"},
            follow_redirects=False,
        )

        assert response.status_code == 307
        mock_create_state.assert_called_once()
        assert mock_create_state.call_args.kwargs["client_type"] == "mobile"

    @patch("modules.auth.identity_providers.public_router.oauth_state_crud.create_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.initiate_login")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    @patch("modules.auth.identity_providers.public_router.idp_utils.validate_redirect_url")
    @patch("modules.auth.identity_providers.public_router.auth_computation.validate_pkce_challenge")
    def test_relative_redirect_uses_request_client_type(
        self,
        mock_validate_pkce,
        mock_validate_redirect,
        mock_get_idp,
        mock_initiate_login,
        mock_create_state,
    ):
        """Test regular web redirects keep using the request header client type."""
        client = _build_app()

        mock_idp = MagicMock(spec=idp_models.IdentityProvider)
        mock_idp.id = 1
        mock_idp.slug = "pocket-id"
        mock_get_idp.return_value = mock_idp
        mock_initiate_login.return_value = "https://provider.example/auth?state=abc"

        response = client.get(
            "/api/v1/public/idp/login/pocket-id",
            params={
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "redirect": "/settings",
            },
            headers={"X-Client-Type": "web"},
            follow_redirects=False,
        )

        assert response.status_code == 307
        mock_create_state.assert_called_once()
        assert mock_create_state.call_args.kwargs["client_type"] == "web"
