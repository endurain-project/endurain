"""The authentication service writes the sign-in, sign-out and refresh-reuse audit trail."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.service as authentication_service

_SERVICE = "modules.auth.authentication.service"
_USER = SimpleNamespace(id=5, username="alice", active=True, access_type="regular")
_LOGIN = authentication_audit_actions.LOGIN.id


def _login(db, *, failed_attempts=None, pending_mfa_store=None, username="alice", client_type="web", **kwargs):
    return authentication_service.login_for_access_token(
        "127.0.0.1",
        "agent",
        username,
        "secret",
        client_type,
        failed_attempts or MagicMock(is_locked_out=MagicMock(return_value=False)),
        pending_mfa_store or MagicMock(),
        MagicMock(),
        MagicMock(),
        db,
        **kwargs,
    )


class TestFailedPasswordSignIn:
    def _authenticate(self, db, *, user, credential=SimpleNamespace(password_hash="hash"), valid=False):
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=user),
            patch(f"{_SERVICE}.credentials_integration.get_credential", return_value=credential),
            patch(f"{_SERVICE}.credentials_integration.verify_and_update_password", return_value=(valid, None)),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            authentication_service.authenticate_user("alice", "secret", MagicMock(), db)

    def test_a_wrong_password_is_a_failure_that_targets_the_user(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._authenticate(mock_db, user=_USER)

        entry = audit.assert_audited(_LOGIN, outcome="failure", target_type="user", target_id="5", target_owner_id="5")
        assert entry.details == {"method": "password", "mfa": False, "reason": "invalid_credentials"}

    def test_an_account_without_a_local_password_is_a_failure_that_targets_the_user(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._authenticate(mock_db, user=_USER, credential=None)

        audit.assert_audited(_LOGIN, outcome="failure", target_id="5")

    def test_an_unknown_username_is_a_failure_with_no_target_and_no_username(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._authenticate(mock_db, user=None)

        entry = audit.assert_audited(_LOGIN, outcome="failure")
        assert entry.target_id is None
        assert entry.target_type is None
        assert "alice" not in repr(entry)


class TestRefusedPasswordSignIn:
    def test_a_locked_out_account_is_denied(self, mock_db):
        failed_attempts = MagicMock()
        failed_attempts.is_locked_out.return_value = True
        failed_attempts.get_lockout_time.return_value = datetime(2999, 1, 1, tzinfo=UTC)
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.TooManyRequestsError):
            _login(mock_db, failed_attempts=failed_attempts)

        entry = audit.assert_audited(_LOGIN, outcome="denied")
        assert entry.details == {"method": "password", "mfa": False, "reason": "locked_out"}
        assert entry.target_id is None

    def test_an_inactive_account_is_denied_and_targets_the_user(self, mock_db):
        user = SimpleNamespace(id=5, username="alice", active=False, access_type="regular")
        with (
            patch(f"{_SERVICE}.authenticate_user", return_value=user),
            patch(f"{_SERVICE}.lockout_integration.report_lockout_applied"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _login(mock_db)

        entry = audit.assert_audited(_LOGIN, outcome="denied", target_id="5", target_owner_id="5")
        assert entry.details["reason"] == "inactive"
        assert len(audit.matching(_LOGIN)) == 1

    def test_disabled_password_sign_in_is_denied_and_targets_the_user(self, mock_db):
        with (
            patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=False),
            patch(f"{_SERVICE}.lockout_integration.report_lockout_applied"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _login(mock_db)

        entry = audit.assert_audited(_LOGIN, outcome="denied", target_id="5")
        assert entry.details["reason"] == "password_sign_in_disabled"

    def test_a_password_that_needs_mfa_is_not_a_sign_in(self, mock_db):
        with (
            patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=True),
            jasil_testing.capture_audit() as audit,
        ):
            _login(mock_db, pending_mfa_store=MagicMock(add_pending_login=MagicMock(return_value="challenge")))

        audit.assert_not_audited(_LOGIN)


class TestSuccessfulSignIn:
    def _login_without_mfa(self, db, **kwargs):
        tokens = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
        with (
            patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            patch(f"{_SERVICE}.create_tokens", return_value=tokens),
            patch(f"{_SERVICE}.sessions_integration.create_session"),
        ):
            return _login(db, **kwargs)

    def test_a_password_sign_in_is_audited_in_the_transaction_that_creates_the_session(self, mock_db):
        mock_db.commit.side_effect = lambda: audit.assert_audited(_LOGIN)
        with jasil_testing.capture_audit() as audit:
            self._login_without_mfa(mock_db)

        entry = audit.assert_audited(
            _LOGIN, outcome="success", actor_type="user", actor_id="5", credential_type="password", target_id="5"
        )
        assert entry.target_owner_id == "5"
        assert entry.details == {"method": "password", "mfa": False, "reason": None}

    def test_a_mobile_pkce_sign_in_is_audited_too(self, mock_db):
        challenge = "a" * 43
        with (
            patch(f"{_SERVICE}.create_mobile_pkce_session_response") as pkce,
            patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            jasil_testing.capture_audit() as audit,
        ):
            _login(mock_db, client_type="mobile", code_challenge=challenge, code_challenge_method="S256")

        pkce.assert_called_once()
        audit.assert_audited(_LOGIN, outcome="success", target_id="5")


class TestMfaSignIn:
    def _verify(self, db, *, code_valid, pending_mfa_store=None):
        store = pending_mfa_store or MagicMock()
        store.get_pending_login.return_value = 5
        store.claim_pending_login.return_value = 5
        store.is_locked_out.return_value = False
        store.record_failed_attempt.return_value = 1
        request = SimpleNamespace(mfa_challenge="challenge", mfa_code="123456")
        tokens = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=_USER),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=code_valid),
            patch(f"{_SERVICE}.lockout_integration.report_lockout_applied"),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch(f"{_SERVICE}.create_tokens", return_value=tokens),
            patch(f"{_SERVICE}.sessions_integration.create_session"),
        ):
            return authentication_service.verify_mfa_and_login(
                "127.0.0.1",
                "agent",
                request,
                "web",
                MagicMock(),
                store,
                MagicMock(),
                MagicMock(),
                db,
            )

    def test_a_wrong_code_is_a_failure_that_targets_the_user(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidMfaCodeError):
            self._verify(mock_db, code_valid=False)

        entry = audit.assert_audited(_LOGIN, outcome="failure", target_id="5", target_owner_id="5")
        assert entry.details == {"method": "password", "mfa": True, "reason": "invalid_mfa_code"}

    def test_a_locked_out_mfa_step_is_denied(self, mock_db):
        store = MagicMock()
        store.is_locked_out.return_value = True
        store.get_lockout_time.return_value = datetime(2999, 1, 1, tzinfo=UTC)
        store.get_pending_login.return_value = 5
        request = SimpleNamespace(mfa_challenge="challenge", mfa_code="123456")
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=_USER),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            authentication_service.verify_mfa_and_login(
                "127.0.0.1", "agent", request, "web", MagicMock(), store, MagicMock(), MagicMock(), mock_db
            )

        entry = audit.assert_audited(_LOGIN, outcome="denied", target_id="5")
        assert entry.details == {"method": "password", "mfa": True, "reason": "locked_out"}

    def test_a_completed_mfa_sign_in_is_audited_with_the_second_factor(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._verify(mock_db, code_valid=True)

        entry = audit.assert_audited(_LOGIN, outcome="success", actor_id="5", credential_type="password", target_id="5")
        assert entry.details == {"method": "password", "mfa": True, "reason": None}


class TestLogoutAndReuse:
    def _session(self):
        return SimpleNamespace(
            id="sid", user_id=1, token_family_id="family", refresh_token="hash", csrf_token_hash=None, rotation_count=0
        )

    def test_a_logout_is_audited_in_the_transaction_that_deletes_the_session(self, mock_db):
        hasher = MagicMock()
        hasher.verify_password.return_value = True
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=self._session()),
            patch(f"{_SERVICE}.sessions_integration.delete_session"),
            patch(f"{_SERVICE}.identity_providers_integration.clear_all_idp_tokens"),
            jasil_testing.capture_audit() as audit,
        ):
            authentication_service.logout(lambda: None, "sid", "rt", "web", 1, hasher, mock_db)

        audit.assert_audited(
            authentication_audit_actions.LOGOUT.id,
            outcome="success",
            actor_id="1",
            target_type="user",
            target_id="1",
            target_owner_id="1",
        )

    def test_a_logout_without_a_live_session_writes_nothing(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=None),
            jasil_testing.capture_audit() as audit,
        ):
            authentication_service.logout(lambda: None, "sid", "rt", "web", 1, MagicMock(), mock_db)

        audit.assert_not_audited(authentication_audit_actions.LOGOUT.id)

    def test_a_replayed_refresh_token_is_denied_and_targets_the_user(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=self._session()),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(f"{_SERVICE}.rotated_refresh_tokens_integration.check_token_reuse", return_value=(True, False)),
            patch(f"{_SERVICE}.sessions_integration.invalidate_token_family"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            authentication_service.refresh_token(
                "127.0.0.1",
                "agent",
                lambda: None,
                1,
                "sid",
                "old",
                datetime(2999, 1, 1, tzinfo=UTC),
                MagicMock(),
                MagicMock(),
                "web",
                mock_db,
            )

        audit.assert_audited(
            authentication_audit_actions.REFRESH_TOKEN_REUSE.id,
            outcome="denied",
            actor_id="1",
            target_type="user",
            target_id="1",
            target_owner_id="1",
        )

    def test_a_replay_inside_the_grace_window_writes_nothing(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=self._session()),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(f"{_SERVICE}.rotated_refresh_tokens_integration.check_token_reuse", return_value=(True, True)),
            patch(f"{_SERVICE}._replay_rotation"),
            jasil_testing.capture_audit() as audit,
        ):
            authentication_service.refresh_token(
                "127.0.0.1",
                "agent",
                lambda: None,
                1,
                "sid",
                "old",
                datetime(2999, 1, 1, tzinfo=UTC),
                MagicMock(),
                MagicMock(),
                "web",
                mock_db,
            )

        audit.assert_not_audited(authentication_audit_actions.REFRESH_TOKEN_REUSE.id)


class TestSsoSignIn:
    def _exchange(self, db, *, idp_id, mfa_enabled=False, mfa_code=None):
        oauth_state = SimpleNamespace(
            id="state",
            purpose="login",
            code_challenge="c",
            code_challenge_method="S256",
            client_type="web",
            idp_id=idp_id,
        )
        session = SimpleNamespace(user_id=5, tokens_exchanged=False)
        tokens = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
        hasher = MagicMock()
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state", return_value=(session, oauth_state)),
            patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier"),
            patch(f"{_SERVICE}.users_integration.require_user", return_value=_USER),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=mfa_enabled),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=True),
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch(f"{_SERVICE}.create_tokens", return_value=tokens),
            patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=True),
        ):
            return authentication_service.exchange_tokens_for_session(
                "sid",
                "verifier",
                mfa_code,
                "web",
                MagicMock(is_locked_out=MagicMock(return_value=False)),
                hasher,
                MagicMock(),
                db,
            )

    def test_an_sso_sign_in_is_audited_when_its_tokens_are_issued(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._exchange(mock_db, idp_id=3)

        entry = audit.assert_audited(
            _LOGIN, outcome="success", actor_id="5", credential_type="oauth", target_type="user", target_id="5"
        )
        assert entry.details == {"method": "identity_provider", "mfa": False, "reason": None}

    def test_an_sso_sign_in_with_a_second_factor_records_it(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._exchange(mock_db, idp_id=3, mfa_enabled=True, mfa_code="123456")

        assert audit.assert_audited(_LOGIN, outcome="success").details["mfa"] is True

    def test_a_password_session_is_not_audited_a_second_time(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._exchange(mock_db, idp_id=None)

        audit.assert_not_audited(_LOGIN)
