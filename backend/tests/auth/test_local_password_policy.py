"""Who may use a local password: accounts that have one, and only administrators while local sign-in is off."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.authentication.service as authentication_service
import modules.auth.credentials.service as credentials_service
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.password_reset_tokens.service as password_reset_service


def _settings(local_login_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(local_login_enabled=local_login_enabled)


def _user(access_type: str = "regular") -> SimpleNamespace:
    return SimpleNamespace(id=7, username="alice", active=True, access_type=access_type)


class TestAllowsPasswordSignIn:
    @pytest.mark.parametrize(
        ("enabled", "access_type", "allowed"),
        [(True, "regular", True), (True, "admin", True), (False, "admin", True), (False, "regular", False)],
    )
    def test_only_administrators_keep_it_while_local_sign_in_is_off(self, enabled, access_type, allowed):
        assert credentials_service.allows_password_sign_in(_settings(enabled), access_type) is allowed


class TestPasswordLogin:
    def _login(self, user, *, local_login_enabled):
        failed_attempts = MagicMock()
        failed_attempts.is_locked_out.return_value = False
        failed_attempts.record_failed_attempt.return_value = 1
        with (
            patch.object(authentication_service, "authenticate_user", return_value=user),
            patch.object(
                authentication_service.server_settings_integration,
                "get_server_settings",
                return_value=_settings(local_login_enabled),
            ),
            patch.object(authentication_service.mfa_integration, "is_mfa_enabled_for_user", return_value=False),
            patch.object(authentication_service, "_finish_login", return_value="tokens") as finish,
        ):
            try:
                result = authentication_service.login_for_access_token(
                    "1.2.3.4",
                    "ua",
                    "alice",
                    "right-password",
                    "web",
                    failed_attempts,
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                    MagicMock(),
                )
            except core_exceptions.UnauthenticatedError as err:
                return err, failed_attempts, finish
        return result, failed_attempts, finish

    def test_a_regular_user_is_refused_like_a_wrong_password_while_local_sign_in_is_off(self):
        result, failed_attempts, finish = self._login(_user(), local_login_enabled=False)

        assert isinstance(result, core_exceptions.UnauthenticatedError)
        assert result.detail == "Unable to authenticate with provided credentials"
        failed_attempts.record_failed_attempt.assert_called_once_with("alice", "1.2.3.4")
        finish.assert_not_called()

    def test_an_administrator_still_signs_in_while_local_sign_in_is_off(self):
        result, _, _ = self._login(_user("admin"), local_login_enabled=False)

        assert result == "tokens"

    def test_a_regular_user_signs_in_while_local_sign_in_is_on(self):
        result, _, _ = self._login(_user(), local_login_enabled=True)

        assert result == "tokens"


class TestPasswordReset:
    @pytest.fixture
    def policy(self):
        with (
            patch.object(password_reset_service.server_settings_integration, "is_mail_configured", return_value=True),
            patch.object(password_reset_service.server_settings_integration, "get_server_settings") as settings,
            patch.object(password_reset_service.credentials_integration, "has_local_password") as has_password,
            patch.object(password_reset_service.core_email_cooldown, "claim_email", return_value=True),
            patch.object(
                password_reset_service.password_reset_event_publishers, "publish_password_reset_requested"
            ) as publish,
        ):
            settings.return_value = _settings(True)
            has_password.return_value = True
            yield SimpleNamespace(settings=settings, has_password=has_password, publish=publish)

    def _request(self, user):
        with patch.object(password_reset_service.users_integration, "get_user_by_email", return_value=user):
            password_reset_service.request_password_reset_email("alice@example.com", MagicMock(), MagicMock())

    def test_an_account_with_a_password_gets_the_email(self, policy):
        self._request(_user())

        policy.publish.assert_called_once()

    def test_an_account_without_a_password_gets_nothing(self, policy):
        policy.has_password.return_value = False

        self._request(_user())

        policy.publish.assert_not_called()

    def test_a_regular_user_gets_nothing_while_local_sign_in_is_off(self, policy):
        policy.settings.return_value = _settings(False)

        self._request(_user())

        policy.publish.assert_not_called()

    def test_an_administrator_still_gets_it_while_local_sign_in_is_off(self, policy):
        policy.settings.return_value = _settings(False)

        self._request(_user("admin"))

        policy.publish.assert_called_once()

    @pytest.mark.parametrize(
        ("has_password", "local_login_enabled"), [(False, True), (True, False)], ids=["no-password", "local-off"]
    )
    def test_an_issued_link_cannot_set_a_password_the_policy_forbids(self, policy, has_password, local_login_enabled):
        policy.has_password.return_value = has_password
        policy.settings.return_value = _settings(local_login_enabled)
        with (
            patch.object(password_reset_service.password_reset_crud, "claim_password_reset_token", return_value=7),
            patch.object(password_reset_service.users_integration, "require_user", return_value=_user()),
            patch.object(password_reset_service.credentials_integration, "set_local_password_hash") as set_hash,
            pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired password reset token"),
        ):
            password_reset_service.use_password_reset_token("token", "N3w-Passw0rd!", MagicMock())

        set_hash.assert_not_called()


class TestFirstPassword:
    def test_an_account_without_a_password_cannot_set_one_itself(self):
        with (
            patch.object(account_security_service.credentials_integration, "has_local_password", return_value=False),
            patch.object(account_security_service.step_up_service, "verify_step_up_credentials") as step_up,
            patch.object(account_security_service.credentials_integration, "set_local_password_hash") as set_hash,
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            account_security_service.stage_change_own_password(
                7, "anything", "N3w-Passw0rd!", None, MagicMock(), MagicMock()
            )

        step_up.assert_not_called()
        set_hash.assert_not_called()


class TestTokenExchange:
    @pytest.mark.parametrize(
        "purpose", [oauth_state_constants.OAuthStatePurpose.LINK, oauth_state_constants.OAuthStatePurpose.STEP_UP]
    )
    def test_only_a_login_state_can_be_exchanged_for_tokens(self, purpose):
        session = SimpleNamespace(tokens_exchanged=False, user_id=7)
        oauth_state = SimpleNamespace(
            id="state-id", purpose=purpose, code_challenge="c" * 43, code_challenge_method="S256"
        )
        with (
            patch.object(
                authentication_service.sessions_integration,
                "get_session_with_oauth_state",
                return_value=(session, oauth_state),
            ),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            authentication_service.exchange_tokens_for_session(
                "session-id", "v" * 43, None, None, MagicMock(), MagicMock(), MagicMock(), MagicMock()
            )
