"""Additional tests for the public identity provider router (uncovered paths)."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.public_router as public_router
import modules.auth.identity_providers.service as idp_service_module
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.schema as users_schema

public_router.idp_crud = idp_crud
public_router.idp_service = MagicMock(idp_service=MagicMock())
public_router.auth_sessions_utils = sessions_integration
public_router.users_schema = users_schema
_test_service = public_router.idp_service.idp_service
_test_service.get_enabled_identity_providers.side_effect = lambda db: idp_crud.get_enabled_identity_providers(db)
_test_service.get_identity_provider_by_slug.side_effect = lambda slug, db: idp_crud.get_identity_provider_by_slug(
    slug, db
)


def _create_callback_session(user, request, password_hasher, db, oauth_state_id):
    idp_service_module.users_integration.require_active_user(user)
    session_user = users_schema.UsersRead.model_validate(user)
    sessions_integration.create_session(
        "test-session-id", session_user, request, None, password_hasher, None, db, oauth_state_id=oauth_state_id
    )
    return "test-session-id"


_test_service.create_callback_session.side_effect = _create_callback_session


def _build_app(mock_db) -> TestClient:
    import core.database as core_db

    app = FastAPI()
    app.include_router(public_router.router, prefix="/api/v1/public/idp")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    app.dependency_overrides[idp_dependencies.get_identity_provider_service] = lambda: _test_service
    return TestClient(app)


class TestGetEnabledProviders:
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_enabled_identity_providers")
    def test_success(self, mock_get, mock_db):
        client = _build_app(mock_db)
        provider = MagicMock()
        provider.id = 1
        provider.name = "Google"
        provider.slug = "google"
        provider.icon = "google-icon"
        mock_get.return_value = [provider]

        response = client.get("/api/v1/public/idp")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Google"

    @patch("modules.auth.identity_providers.public_router.idp_crud.get_enabled_identity_providers")
    def test_empty(self, mock_get, mock_db):
        client = _build_app(mock_db)
        mock_get.return_value = []

        response = client.get("/api/v1/public/idp")
        assert response.status_code == 200
        assert response.json() == []


class TestInitiateLoginErrors:
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_provider_not_found(self, mock_get_idp, mock_db):
        client = _build_app(mock_db)
        mock_get_idp.return_value = None

        response = client.get(
            "/api/v1/public/idp/login/unknown",
            params={
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
            },
        )
        assert response.status_code == 404

    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_provider_disabled(self, mock_get_idp, mock_db):
        client = _build_app(mock_db)
        idp = MagicMock()
        idp.enabled = False
        mock_get_idp.return_value = idp

        response = client.get(
            "/api/v1/public/idp/login/disabled",
            params={
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
            },
        )
        assert response.status_code == 404

    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    @patch("modules.auth.identity_providers.public_router.auth_computation.validate_pkce_challenge")
    @patch("modules.auth.identity_providers.public_router.idp_utils.validate_redirect_url")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.initiate_login")
    def test_generic_exception(self, mock_login, mock_val_url, mock_val_pkce, mock_get_idp, mock_db):
        client = _build_app(mock_db)
        idp = MagicMock()
        idp.enabled = True
        idp.slug = "test"
        idp.id = 1
        mock_get_idp.return_value = idp
        mock_login.side_effect = Exception("Unexpected error")

        response = client.get(
            "/api/v1/public/idp/login/test",
            params={
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
            },
        )
        assert response.status_code == 500

    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    @patch("modules.auth.identity_providers.public_router.auth_computation.validate_pkce_challenge")
    @patch("modules.auth.identity_providers.public_router.idp_utils.validate_redirect_url")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.initiate_login")
    @patch("modules.auth.identity_providers.public_router.idp_utils.is_custom_scheme_redirect")
    @patch.object(_test_service, "create_login_oauth_state", return_value="state-id")
    def test_invalid_client_type_defaults_to_web(
        self,
        mock_create_state,
        mock_custom_scheme,
        mock_login,
        mock_val_url,
        mock_val_pkce,
        mock_get_idp,
        mock_db,
    ):
        client = _build_app(mock_db)
        idp = MagicMock()
        idp.enabled = True
        idp.slug = "test"
        idp.id = 1
        mock_get_idp.return_value = idp
        mock_custom_scheme.return_value = False
        mock_login.return_value = "https://provider.example/auth"

        response = client.get(
            "/api/v1/public/idp/login/test",
            params={
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
            },
            headers={"X-Client-Type": "desktop"},
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert mock_create_state.call_args.kwargs["client_type"] == "web"


class TestHandleCallback:
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_provider_not_found(self, mock_get_idp, mock_db):
        client = _build_app(mock_db)
        mock_get_idp.return_value = None

        response = client.get(
            "/api/v1/public/idp/callback/test?code=abc&state=xyz",
            follow_redirects=False,
        )
        assert response.status_code == 404

    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    @patch.object(_test_service, "get_unused_oauth_state")
    def test_oauth_state_not_found(self, mock_get_state, mock_get_idp, mock_db):
        client = _build_app(mock_db)
        idp = MagicMock()
        idp.enabled = True
        idp.name = "Test"
        mock_get_idp.return_value = idp
        mock_get_state.return_value = None

        response = client.get(
            "/api/v1/public/idp/callback/test?code=abc&state=invalid",
            follow_redirects=False,
        )
        assert response.status_code == 400

    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch.object(_test_service, "claim_oauth_state")
    def test_state_replay(self, mock_mark_used, mock_get_state, mock_get_idp, mock_db):
        client = _build_app(mock_db)
        idp = MagicMock()
        idp.enabled = True
        idp.name = "Test"
        idp.slug = "test"
        mock_get_idp.return_value = idp
        oauth_state = MagicMock()
        oauth_state.client_type = "web"
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = False

        response = client.get(
            "/api/v1/public/idp/callback/test?code=abc&state=replayed",
            follow_redirects=False,
        )
        assert response.status_code == 400


class TestAppendQueryParams:
    def test_appends_to_path_without_query(self):
        result = public_router._append_query_params("/settings/security", {"idp_link": "success"})
        assert result == "/settings/security?idp_link=success"

    def test_preserves_existing_query(self):
        result = public_router._append_query_params("/settings?tab=security", {"idp_link": "success"})
        assert result == "/settings?tab=security&idp_link=success"

    def test_url_encodes_values(self):
        result = public_router._append_query_params("/settings/security", {"idp_name": "My IdP"})
        assert result == "/settings/security?idp_name=My+IdP"


class TestBuildLinkResultUrl:
    HOST = "https://app.example.com"

    def _patch_host(self):
        return patch.object(public_router.core_config.settings, "ENDURAIN_HOST", self.HOST)

    def test_default_path_when_no_return_path(self):
        with self._patch_host():
            result = public_router._build_link_result_url(None, "Google", success=True)
        assert result == f"{self.HOST}/settings/security?idp_link=success&idp_name=Google"

    def test_honors_relative_return_path(self):
        with self._patch_host():
            result = public_router._build_link_result_url("/settings/security", "Google", success=True)
        assert result == f"{self.HOST}/settings/security?idp_link=success&idp_name=Google"

    def test_custom_scheme_is_not_host_prefixed(self):
        with self._patch_host():
            result = public_router._build_link_result_url("gadgetbridge://callback", "Google", success=True)
        assert result == "gadgetbridge://callback?idp_link=success&idp_name=Google"

    def test_error_omits_idp_name(self):
        with self._patch_host():
            result = public_router._build_link_result_url("/settings/security", None, success=False)
        assert result == f"{self.HOST}/settings/security?idp_link=error"

    def test_error_falls_back_to_default_path(self):
        with self._patch_host():
            result = public_router._build_link_result_url(None, None, success=False)
        assert result == f"{self.HOST}/settings/security?idp_link=error"


class TestHandleCallbackRedirects:
    """Cover the success and error redirect paths of handle_callback."""

    @staticmethod
    def _enabled_idp() -> MagicMock:
        idp = MagicMock()
        idp.enabled = True
        idp.id = 1
        idp.name = "Google"
        idp.slug = "google"
        return idp

    @staticmethod
    def _valid_state() -> MagicMock:
        oauth_state = MagicMock()
        oauth_state.client_type = "web"
        # Matches idp.id so the state/IdP binding check passes.
        oauth_state.idp_id = 1
        return oauth_state

    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_link_mode_success_redirects_to_link_result_url(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_db,
    ):
        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        oauth_state.user_id = 5
        oauth_state.redirect_path = "/settings/security"
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        user = MagicMock()
        user.username = "alice"
        mock_handle_callback.return_value = {"user": user, "mode": "link"}

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        assert "idp_link=success" in response.headers["location"]

    @patch("modules.auth.identity_providers.public_router.auth_sessions_utils.create_session")
    @patch("modules.auth.identity_providers.public_router.users_schema.UsersRead.model_validate")
    @patch("modules.auth.identity_providers.service.users_integration.require_active_user")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_login_mode_success_redirects_with_session_id(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_check_active,
        mock_model_validate,
        mock_create_session,
        mock_db,
    ):
        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        oauth_state.user_id = None
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        user = MagicMock()
        user.username = "alice"
        mock_handle_callback.return_value = {"user": user, "mode": "login"}

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        location = response.headers["location"]
        assert "sso=success" in location
        assert "session_id=" in location
        mock_create_session.assert_called_once()

    @patch("modules.auth.identity_providers.public_router.auth_sessions_utils.create_session")
    @patch("modules.auth.identity_providers.public_router.users_schema.UsersRead.model_validate")
    @patch("modules.auth.identity_providers.service.users_integration.require_active_user")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_login_mode_appends_relative_redirect_path(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_check_active,
        mock_model_validate,
        mock_create_session,
        mock_db,
    ):
        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        oauth_state.user_id = None
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        user = MagicMock()
        user.username = "alice"
        mock_handle_callback.return_value = {
            "user": user,
            "mode": "login",
            "redirect_path": "/dashboard",
        }

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        location = response.headers["location"]
        assert "redirect=/dashboard" in location
        assert "external_redirect=true" not in location

    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.log_public_flow_event")
    @patch("modules.auth.identity_providers.public_router.auth_sessions_utils.create_session")
    @patch("modules.auth.identity_providers.public_router.users_schema.UsersRead.model_validate")
    @patch("modules.auth.identity_providers.service.users_integration.require_active_user")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_login_mode_encodes_the_redirect_and_does_not_log_the_session_id(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_check_active,
        mock_model_validate,
        mock_create_session,
        mock_logger,
        mock_db,
    ):
        from urllib.parse import parse_qs, urlsplit

        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        oauth_state.user_id = None
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        user = MagicMock()
        user.username = "alice"
        mock_handle_callback.return_value = {
            "user": user,
            "mode": "login",
            "redirect_path": "/settings?tab=security&session_id=attacker#top",
        }

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        query = parse_qs(urlsplit(response.headers["location"]).query)
        # The path's own "&" and "#" must not become parameters of the login URL.
        assert query["redirect"] == ["/settings?tab=security&session_id=attacker#top"]
        assert len(query["session_id"]) == 1
        session_id = query["session_id"][0]
        assert session_id != "attacker"
        logged = " ".join(str(call) for call in mock_logger.call_args_list)
        assert "SSO login successful" in logged
        assert session_id not in logged

    @patch("modules.auth.identity_providers.public_router.auth_sessions_utils.create_session")
    @patch("modules.auth.identity_providers.public_router.users_schema.UsersRead.model_validate")
    @patch("modules.auth.identity_providers.service.users_integration.require_active_user")
    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_login_mode_custom_scheme_sets_external_redirect_flag(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_check_active,
        mock_model_validate,
        mock_create_session,
        mock_db,
    ):
        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        oauth_state.user_id = None
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        user = MagicMock()
        user.username = "alice"
        mock_handle_callback.return_value = {
            "user": user,
            "mode": "login",
            "redirect_path": "gadgetbridge://endurain/oauth/callback",
        }

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        assert "external_redirect=true" in response.headers["location"]

    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_login_failure_redirects_to_login_error(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_db,
    ):
        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        # No user_id => login attempt => error falls back to the login page.
        oauth_state.user_id = None
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        mock_handle_callback.side_effect = Exception("boom")

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        assert "error=sso_failed" in response.headers["location"]

    @patch("modules.auth.identity_providers.public_router.idp_service.idp_service.handle_callback")
    @patch.object(_test_service, "claim_oauth_state")
    @patch.object(_test_service, "get_unused_oauth_state")
    @patch("modules.auth.identity_providers.public_router.idp_crud.get_identity_provider_by_slug")
    def test_link_failure_redirects_to_link_error(
        self,
        mock_get_idp,
        mock_get_state,
        mock_mark_used,
        mock_handle_callback,
        mock_db,
    ):
        client = _build_app(mock_db)
        mock_get_idp.return_value = self._enabled_idp()
        oauth_state = self._valid_state()
        # user_id set => link attempt => error returns to the originating page.
        oauth_state.user_id = 5
        oauth_state.redirect_path = "/settings/security"
        mock_get_state.return_value = oauth_state
        mock_mark_used.return_value = True
        mock_handle_callback.side_effect = Exception("boom")

        response = client.get(
            "/api/v1/public/idp/callback/google?code=abc&state=xyz",
            follow_redirects=False,
        )

        assert response.status_code == 307
        assert "idp_link=error" in response.headers["location"]
