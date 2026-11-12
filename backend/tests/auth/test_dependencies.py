"""Tests for app/auth/dependencies.py.

Covers all public functions and async dependencies defined in the module.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from fastapi.security import SecurityScopes

import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.schema as auth_schema
from modules.auth.contracts import AccessTokenCred, ApiKeyCred, PasswordCred, Principal
from modules.auth.dependencies import (
    _require_scopes,
    authenticate,
    check_scopes,
    get_current_scopes,
    get_current_user_id,
    get_principal,
    get_sid_from_access_token,
)
from modules.auth.identity_providers.constants import StepUpAction


def _principal(credential=None, scopes: frozenset[str] = frozenset({"account"}), user_id: int = 5) -> Principal:
    return Principal(
        user_id=user_id,
        username="u",
        email="u@e.com",
        is_active=True,
        is_superuser=False,
        scopes=scopes,
        credential=credential or PasswordCred(username="u"),
    )


def _request(query: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    request.state = SimpleNamespace()
    request.query_params = query or {}
    return request


class TestGetPrincipal:
    """Tests for get_principal, the one resolver of an access token or API key."""

    def test_is_sync_so_blocking_lookups_run_in_the_threadpool(self):
        assert not inspect.iscoroutinefunction(get_principal)

    def test_a_cached_principal_is_returned_without_resolving_again(self):
        request = _request()
        request.state.principal = _principal()
        with patch("modules.auth.dependencies.authentication_integration.resolve_from_access_token") as resolve:
            assert get_principal(request, MagicMock(), "token", None, MagicMock()) is request.state.principal
        resolve.assert_not_called()

    @patch("modules.auth.dependencies.authentication_integration.resolve_from_access_token")
    def test_an_access_token_resolves_via_integration_and_is_cached(self, mock_resolve):
        request = _request()
        db = MagicMock()
        mock_resolve.return_value = _principal(user_id=7)

        result = get_principal(request, db, "bearer-token", None, MagicMock())

        assert result.user_id == 7
        assert request.state.principal is result
        mock_resolve.assert_called_once_with("bearer-token", db)

    @patch("modules.auth.dependencies.authentication_integration.resolve_from_api_key")
    def test_an_api_key_header_resolves_via_integration(self, mock_resolve):
        request = _request()
        db = MagicMock()
        mock_resolve.return_value = _principal(ApiKeyCred(api_key_id="2", key_prefix="sk"), user_id=8)

        result = get_principal(request, db, None, "sk-123", MagicMock())

        assert result.user_id == 8
        assert result.is_api_key()
        mock_resolve.assert_called_once_with("sk-123", request, db)

    def test_the_api_key_query_string_is_ignored_when_disabled(self):
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = False
        with (
            patch("modules.auth.dependencies.core_config.settings", mock_settings),
            patch("modules.auth.dependencies.authentication_integration.resolve_from_api_key") as mock_resolve,
            pytest.raises(core_exceptions.UnauthenticatedError) as exc_info,
        ):
            get_principal(_request({"api_key": "qk-456"}), MagicMock(), None, None, MagicMock())
        assert exc_info.value.status_code == 401
        mock_resolve.assert_not_called()

    @patch("modules.auth.dependencies.authentication_integration.resolve_from_api_key")
    def test_the_api_key_query_string_is_accepted_when_enabled(self, mock_resolve):
        request = _request({"api_key": "qk-456"})
        db = MagicMock()
        mock_resolve.return_value = _principal(ApiKeyCred(api_key_id="3", key_prefix="qk"), user_id=9)
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = True
        with patch("modules.auth.dependencies.core_config.settings", mock_settings):
            result = get_principal(request, db, None, None, MagicMock())
        assert result.user_id == 9
        mock_resolve.assert_called_once_with("qk-456", request, db)

    def test_no_credentials_raises_401(self):
        with pytest.raises(core_exceptions.UnauthenticatedError) as exc_info:
            get_principal(_request(), MagicMock(), None, None, MagicMock())
        assert exc_info.value.status_code == 401


class TestCallerDependencies:
    """The dependencies a route reads its caller through all take it from the resolved principal."""

    def test_authenticate_accepts_any_resolved_caller(self):
        assert authenticate(_principal(ApiKeyCred(api_key_id="1", key_prefix="k"))) is None

    def test_get_current_user_id_returns_the_callers_id(self):
        assert get_current_user_id(_principal(user_id=5)) == 5

    def test_get_current_scopes_returns_the_callers_scopes(self):
        assert get_current_scopes(_principal(scopes=frozenset({"gears:read"}))) == frozenset({"gears:read"})

    def test_the_session_id_of_an_access_token_is_returned(self):
        assert get_sid_from_access_token(_principal(AccessTokenCred(session_id="sid-1"))) == "sid-1"

    def test_an_api_key_has_no_session_and_is_refused_with_403(self):
        with pytest.raises(core_exceptions.PermissionDeniedError) as exc_info:
            get_sid_from_access_token(_principal(ApiKeyCred(api_key_id="1", key_prefix="k")))
        assert exc_info.value.status_code == 403
        assert "signed-in session" in exc_info.value.detail


class TestCheckScopes:
    """Tests for check_scopes."""

    def test_all_scopes_present_no_exception(self):
        check_scopes(_principal(scopes=frozenset({"account", "read"})), SecurityScopes(scopes=["account"]))

    def test_missing_scopes_raises_403(self):
        with pytest.raises(core_exceptions.PermissionDeniedError) as exc_info:
            check_scopes(_principal(), SecurityScopes(scopes=["account", "admin"]))
        assert exc_info.value.status_code == 403

    def test_the_challenge_names_the_scopes_the_route_requires_as_a_space_separated_list(self):
        with pytest.raises(core_exceptions.PermissionDeniedError) as exc_info:
            check_scopes(_principal(), SecurityScopes(scopes=["account", "activities:read", "activities:write"]))
        assert exc_info.value.headers == {
            "WWW-Authenticate": 'Bearer error="insufficient_scope", scope="account activities:read activities:write"'
        }

    def test_the_missing_scopes_are_an_extension_member_not_a_python_repr(self):
        with pytest.raises(core_exceptions.PermissionDeniedError) as exc_info:
            check_scopes(_principal(), SecurityScopes(scopes=["account", "users:write", "activities:read"]))
        assert exc_info.value.extensions == {"missing_scopes": ["activities:read", "users:write"]}
        assert exc_info.value.detail == "Missing permissions: activities:read, users:write"


class TestAuditContextFromRequest:
    """The audit context names the request's principal, or the system outside a request."""

    @staticmethod
    def _request(principal=None, ip="203.0.113.7", user_agent="Mozilla/5.0"):
        from starlette.requests import Request

        headers = [(b"user-agent", user_agent.encode())] if user_agent else []
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": headers, "client": (ip, 1234)})
        if principal is not None:
            request.state.principal = principal
        return request

    @staticmethod
    def _principal(credential):
        return Principal(
            user_id=42,
            username="alice",
            email="alice@example.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset(),
            credential=credential,
        )

    def _context(self, request):
        with patch.object(auth_dependencies.core_request_context, "get_current_request", return_value=request):
            return auth_dependencies.audit_context_from_request()

    def test_outside_a_request_the_system_acts(self):
        import jasil.audit as jasil_audit

        context = self._context(None)

        assert context.actor_type is jasil_audit.ActorType.SYSTEM
        assert context.source is jasil_audit.Source.WORKER
        assert context.actor_id is None

    def test_before_authentication_the_client_is_anonymous(self):
        import jasil.audit as jasil_audit

        context = self._context(self._request())

        assert context.actor_type is jasil_audit.ActorType.ANONYMOUS
        assert context.source is jasil_audit.Source.API
        assert context.ip_address == "203.0.113.7"
        assert context.user_agent == "Mozilla/5.0"

    def test_a_session_principal_is_the_user(self):
        import jasil.audit as jasil_audit

        from modules.auth.contracts import AccessTokenCred

        context = self._context(self._request(self._principal(AccessTokenCred(session_id="sid-1"))))

        assert context.actor_type is jasil_audit.ActorType.USER
        assert context.actor_id == "42"
        assert context.credential_type == "access_token"
        assert context.credential_id == "sid-1"

    def test_an_api_key_principal_names_the_key_not_its_value(self):
        import jasil.audit as jasil_audit

        context = self._context(self._request(self._principal(ApiKeyCred(api_key_id=7, key_prefix="end_abc"))))

        assert context.actor_type is jasil_audit.ActorType.API_KEY
        assert context.actor_id == "42"
        assert context.credential_type == "api_key"
        assert context.credential_id == "7"

    def test_an_unknown_client_and_missing_user_agent_are_left_empty(self):
        from starlette.requests import Request

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

        context = self._context(request)

        assert context.ip_address is None
        assert context.user_agent is None


class TestRequireScopesAudit:
    """A refused scope check leaves a denial in the audit trail."""

    def test_a_missing_scope_is_audited_as_denied_with_the_sorted_missing_scopes(self):
        security_scopes = SecurityScopes(scopes=["users:write", "activities:read"])

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.PermissionDeniedError):
            _require_scopes(["account"], security_scopes)

        entry = audit.assert_audited("auth.scope.denied", outcome="denied")
        assert entry.details == {"missing_scopes": ["activities:read", "users:write"]}

    def test_a_granted_scope_writes_nothing(self):
        with jasil_testing.capture_audit() as audit:
            _require_scopes(["account"], SecurityScopes(scopes=["account"]))

        audit.assert_not_audited("auth.scope.denied")


class TestStepUpVerifier:
    """The verifier handed to identity-provider routes is bound to the calling administrator."""

    def test_it_verifies_with_the_administrators_id_session_and_store(self):
        store, db, step_up = MagicMock(), MagicMock(), auth_schema.StepUpVerification(current_password="pw")
        with patch.object(auth_dependencies.account_security_integration, "verify_step_up") as verify:
            verifier = auth_dependencies.get_step_up_verifier(9, "sid-9", store, db)
            verifier(step_up, StepUpAction.ADMIN_IDP_CREATE)

        verify.assert_called_once_with(step_up, 9, "sid-9", StepUpAction.ADMIN_IDP_CREATE, store, db)

    def test_a_refusal_propagates(self):
        with patch.object(
            auth_dependencies.account_security_integration,
            "verify_step_up",
            side_effect=core_exceptions.StepUpFailedError(),
        ):
            verifier = auth_dependencies.get_step_up_verifier(9, "sid-9", MagicMock(), MagicMock())
            with pytest.raises(core_exceptions.StepUpFailedError):
                verifier(auth_schema.StepUpVerification(), StepUpAction.ADMIN_IDP_EDIT)

    def test_it_satisfies_the_identity_provider_contract(self):
        verifier: idp_contracts.StepUpVerifier = auth_dependencies.get_step_up_verifier(
            9, "sid-9", MagicMock(), MagicMock()
        )

        assert callable(verifier)


class TestSessionRevokeVerifier:
    """The verifier handed to the session-revoke routes is bound to the session-revoke action."""

    def test_it_verifies_the_step_up_for_the_revoke_action(self):
        step_up, underlying = auth_schema.StepUpVerification(current_password="pw"), MagicMock()

        auth_dependencies.get_session_revoke_verifier(underlying)(step_up)

        underlying.assert_called_once_with(step_up, StepUpAction.ADMIN_SESSIONS_REVOKE)

    def test_a_refusal_propagates(self):
        underlying = MagicMock(side_effect=core_exceptions.StepUpFailedError())

        with pytest.raises(core_exceptions.StepUpFailedError):
            auth_dependencies.get_session_revoke_verifier(underlying)(auth_schema.StepUpVerification())
