"""The SSO callback audits the sign-ins it refuses as ``auth.session.login`` rows."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.auth.oauth_state.constants as oauth_state_constants

_LOGIN = "auth.session.login"
_PURPOSE = oauth_state_constants.OAuthStatePurpose
_HOST = "https://app.example.com"
_STATE_MESSAGE = "Invalid or expired OAuth state"


@pytest.fixture
def service():
    return callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), _HOST)


def _idp(**overrides):
    values = {
        "id": 1,
        "slug": "test",
        "name": "Test",
        "enabled": True,
        "provider_type": "oauth2",
        "issuer_url": None,
        "userinfo_endpoint": "https://x/userinfo",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _state(**overrides):
    values = {
        "id": "state-id",
        "idp_id": 1,
        "client_type": "web",
        "user_id": None,
        "browser_binding_hash": None,
        "purpose": _PURPOSE.LOGIN,
        "nonce": "n",
        "redirect_path": None,
        "idp_code_verifier": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _assert_refusal(audit, *, outcome, reason, user_id=None):
    target = {"target_type": "user", "target_id": str(user_id), "target_owner_id": str(user_id)} if user_id else {}
    entry = audit.assert_audited(_LOGIN, outcome=outcome, **target)
    assert entry.details == {"method": "identity_provider", "mfa": False, "reason": reason, "new_device": False}
    if not user_id:
        assert entry.target_id is None


class TestStateRefusals:
    def _prepare(self, service, *, idp, oauth_state, claimed=True):
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "get_unused_oauth_state", return_value=oauth_state),
            patch.object(service, "claim_oauth_state", return_value=claimed),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidInputError, match=_STATE_MESSAGE),
        ):
            service.prepare_callback("test", "state-id", None, MagicMock())
        return audit

    def test_an_unknown_state_is_audited(self, service):
        audit = self._prepare(service, idp=_idp(), oauth_state=None)

        _assert_refusal(audit, outcome="failure", reason="invalid_state")

    def test_a_state_of_another_provider_is_audited(self, service):
        audit = self._prepare(service, idp=_idp(id=1), oauth_state=_state(idp_id=2))

        _assert_refusal(audit, outcome="failure", reason="invalid_state")

    def test_a_replayed_state_is_audited(self, service):
        audit = self._prepare(service, idp=_idp(), oauth_state=_state(), claimed=False)

        _assert_refusal(audit, outcome="failure", reason="invalid_state")

    def test_a_refused_link_state_is_not_a_sign_in(self, service):
        audit = self._prepare(service, idp=_idp(id=1), oauth_state=_state(idp_id=2, purpose=_PURPOSE.LINK, user_id=7))

        audit.assert_not_audited(_LOGIN)

    def test_a_missing_provider_is_not_audited(self, service):
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=None),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            service.prepare_callback("test", "state-id", None, MagicMock())

        audit.assert_not_audited(_LOGIN)


class TestCompleteLoginRefusals:
    def _complete(self, service, *, userinfo=None, find_error=None, user=None, session_error=None):
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        get_userinfo = {"side_effect": userinfo} if isinstance(userinfo, Exception) else {"return_value": {"sub": "s"}}
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", **get_userinfo),
            patch.object(
                callback_service.user_provisioning_service,
                "find_or_create_user",
                side_effect=find_error,
                return_value=user,
            ),
            patch.object(callback_service.users_integration, "require_active_user", side_effect=session_error),
            patch.object(callback_service.sessions_integration, "create_session"),
            patch.object(callback_service.server_settings_integration, "get_session_policy"),
            jasil_testing.capture_audit() as audit,
        ):
            url = service.complete_callback(
                _idp(), "code", None, "state", _state(), "10.0.0.1", "agent", MagicMock(), MagicMock()
            )
        return url, audit

    def test_an_invalid_id_token_is_audited(self, service):
        url, audit = self._complete(service, userinfo=core_exceptions.UnauthenticatedError("ID token has expired"))

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="failure", reason="invalid_id_token")

    def test_a_refused_provisioning_is_audited_and_keeps_its_login_error(self, service):
        error = user_provisioning_service.SsoSignInRefusedError("no email", login_error="sso_email_missing")

        url, audit = self._complete(service, find_error=error)

        assert url == f"{_HOST}/login?error=sso_email_missing"
        _assert_refusal(audit, outcome="denied", reason="provisioning_refused")

    def test_a_provisioning_policy_refusal_is_audited(self, service):
        error = core_exceptions.PermissionDeniedError("User account creation is disabled")

        url, audit = self._complete(service, find_error=error)

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="denied", reason="provisioning_refused")

    def test_an_inactive_user_is_audited_with_the_account(self, service):
        user = SimpleNamespace(id=9, username="bob", active=False)

        url, audit = self._complete(
            service, user=user, session_error=core_exceptions.PermissionDeniedError("Inactive user")
        )

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="denied", reason="inactive", user_id=9)

    def test_a_refused_link_is_not_a_login_refusal(self, service):
        error = core_exceptions.NotFoundError("User not found")
        with (
            patch.object(service, "handle_callback", side_effect=error),
            jasil_testing.capture_audit() as audit,
        ):
            service.complete_callback(
                _idp(),
                "code",
                None,
                "state",
                _state(purpose=_PURPOSE.LINK, user_id=7),
                "ip",
                "agent",
                MagicMock(),
                MagicMock(),
            )

        audit.assert_not_audited(_LOGIN)
