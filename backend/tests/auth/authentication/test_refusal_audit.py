"""Refused API keys, refused session refreshes and refused MFA challenges are audited without any secret."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.principal_service as principal_service
import modules.auth.authentication.refresh_service as authentication_service_refresh_service
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.server_settings.contracts as server_settings_contracts
from tests._helpers.auth import pending_login

_SERVICE = "modules.auth.authentication.service"
_PRINCIPAL = "modules.auth.authentication.principal_service"
_API_KEY = authentication_audit_actions.API_KEY_AUTHENTICATE.id
_REFRESH = authentication_audit_actions.REFRESH.id
_LOGIN = login_audit_actions.LOGIN.id
_KEY_HASH = "a" * 64
_USER = SimpleNamespace(id=5, username="alice", email="a@example.com", active=True, access_type="regular")


def _db_key(**overrides):
    values = {
        "id": "key-1",
        "user_id": 5,
        "name": "CLI",
        "key_prefix": "abcd1234",
        "is_active": True,
        "expires_at": datetime.now(UTC) + timedelta(days=30),
        "created_at": datetime.now(UTC),
        "scopes": "[]",
    }
    return api_keys_schema.UserApiKeyRead(**{**values, **overrides})


def _resolve(db_key, *, user=_USER):
    with (
        patch(f"{_PRINCIPAL}.api_keys_integration.hash_api_key", return_value=_KEY_HASH),
        patch(f"{_PRINCIPAL}.api_keys_integration.get_api_key_by_hash", return_value=db_key),
        patch(f"{_PRINCIPAL}.users_integration.require_user", return_value=user),
        patch(
            f"{_PRINCIPAL}.server_settings_integration.get_access_policy",
            return_value=MagicMock(require_mfa=server_settings_contracts.RequireMfa.OFF),
        ),
    ):
        return principal_service.resolve_from_api_key("raw-secret-key", "/api/v1/x", "127.0.0.1", MagicMock())


class TestApiKeyRefusal:
    def test_an_unknown_key_is_a_failure_with_no_target(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            _resolve(None)

        entry = audit.assert_audited(_API_KEY, outcome="failure")
        assert entry.details == {"reason": "unknown_key"}
        assert entry.target_type is None
        assert entry.target_id is None
        assert "raw-secret-key" not in repr(entry)

    def test_a_revoked_key_is_a_failure_that_targets_the_key(self):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            _resolve(_db_key(is_active=False))

        entry = audit.assert_audited(
            _API_KEY, outcome="failure", target_type="api_key", target_id="key-1", target_owner_id="5"
        )
        assert entry.details == {"reason": "revoked"}
        assert "abcd1234" not in repr(entry)

    def test_an_expired_key_is_a_failure_that_targets_the_key(self):
        expired = _db_key(expires_at=datetime.now(UTC) - timedelta(days=1))
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            _resolve(expired)

        entry = audit.assert_audited(
            _API_KEY, outcome="failure", target_type="api_key", target_id="key-1", target_owner_id="5"
        )
        assert entry.details == {"reason": "expired"}

    def test_a_valid_key_of_an_inactive_owner_is_denied(self):
        inactive = SimpleNamespace(id=5, username="alice", active=False, access_type="regular")
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.PermissionDeniedError):
            _resolve(_db_key(), user=inactive)

        entry = audit.assert_audited(
            _API_KEY, outcome="denied", target_type="api_key", target_id="key-1", target_owner_id="5"
        )
        assert entry.details == {"reason": "owner_inactive"}

    def test_an_accepted_key_writes_nothing(self):
        with (
            jasil_testing.capture_audit() as audit,
            patch(f"{_PRINCIPAL}.authentication_event_publishers.publish_api_key_used"),
        ):
            _resolve(_db_key())

        audit.assert_not_audited(_API_KEY)


def _session(**overrides):
    values = {
        "id": "sid",
        "user_id": 5,
        "token_family_id": "family",
        "refresh_token": "hash",
        "csrf_token_hash": None,
        "rotation_count": 0,
        "client_type": auth_constants.ClientType.WEB,
    }
    return SimpleNamespace(**{**values, **overrides})


def _refresh(db, *, session, x_csrf_token=None, hasher=None, token_user_id=5):
    with (
        patch(f"{_SERVICE}.sessions_integration.lock_live_session", return_value=session),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
    ):
        return authentication_service_refresh_service.refresh_token(
            "127.0.0.1",
            "agent",
            token_user_id,
            "sid",
            "old-token",
            datetime(2999, 1, 1, tzinfo=UTC),
            hasher or MagicMock(),
            MagicMock(),
            "web",
            db,
            x_csrf_token,
        )


class TestRefreshRefusal:
    def _assert_refused(self, audit, outcome, reason):
        entry = audit.assert_audited(
            _REFRESH,
            outcome=outcome,
            actor_type="user",
            actor_id="5",
            credential_type="refresh_token",
            target_type="user",
            target_id="5",
            target_owner_id="5",
        )
        assert entry.details == {"reason": reason}
        assert len(audit.matching(_REFRESH)) == 1
        assert "old-token" not in repr(entry)

    def test_a_missing_session_is_a_failure(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidTokenError):
            _refresh(mock_db, session=None)

        self._assert_refused(audit, "failure", "session_not_found")

    def test_a_session_of_another_user_is_a_failure(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            _refresh(mock_db, session=_session(user_id=9))

        self._assert_refused(audit, "failure", "session_owner_mismatch")

    def test_a_session_of_another_client_type_is_a_failure(self, mock_db):
        """A web request cannot refresh a mobile session, nor the reverse."""
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidTokenError):
            _refresh(mock_db, session=_session(client_type=auth_constants.ClientType.MOBILE))

        self._assert_refused(audit, "failure", "client_type_mismatch")

    def test_a_timed_out_session_is_a_failure(self, mock_db):
        with (
            patch(
                f"{_SERVICE}.sessions_integration.validate_session_timeout",
                side_effect=core_exceptions.UnauthenticatedError("Session expired"),
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _refresh(mock_db, session=_session())

        self._assert_refused(audit, "failure", "session_expired")

    def test_a_wrong_csrf_token_is_denied(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(f"{_SERVICE}.sessions_integration.verify_csrf_token", return_value=False),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            _refresh(mock_db, session=_session(csrf_token_hash="h"), x_csrf_token="wrong")

        self._assert_refused(audit, "denied", "invalid_csrf_token")

    def test_a_session_whose_tokens_were_not_exchanged_is_a_failure(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _refresh(mock_db, session=_session(refresh_token=None))

        self._assert_refused(audit, "failure", "tokens_not_exchanged")

    def test_a_token_that_does_not_match_the_session_is_a_failure(self, mock_db):
        hasher = MagicMock()
        hasher.verify_password.return_value = False
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
                return_value=(False, False),
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _refresh(mock_db, session=_session(), hasher=hasher)

        self._assert_refused(audit, "failure", "invalid_token")

    def _refresh_with_valid_token(self, db, *, user):
        hasher = MagicMock()
        hasher.verify_password.return_value = True
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
                return_value=(False, False),
            ),
            patch(f"{_SERVICE}.users_integration.get_user", return_value=user),
        ):
            _refresh(db, session=_session(), hasher=hasher)

    def test_a_missing_user_is_a_failure(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._refresh_with_valid_token(mock_db, user=None)

        self._assert_refused(audit, "failure", "user_not_found")

    def test_an_inactive_user_is_denied(self, mock_db):
        inactive = SimpleNamespace(id=5, username="alice", active=False, access_type="regular")
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.InvalidTokenError):
            self._refresh_with_valid_token(mock_db, user=inactive)

        self._assert_refused(audit, "denied", "user_inactive")

    def test_a_replay_with_no_stored_replacement_is_a_failure(self, mock_db):
        with (
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token",
                return_value=None,
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            authentication_service_refresh_service._replay_rotation(
                "web", _session(), "old-token", "127.0.0.1", "agent", 5, MagicMock(), MagicMock(), mock_db
            )

        self._assert_refused(audit, "failure", "replay_unavailable")

    def test_a_replay_for_a_missing_user_is_a_failure(self, mock_db):
        with (
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token",
                return_value=("replacement", datetime(2999, 1, 1, tzinfo=UTC)),
            ),
            patch(f"{_SERVICE}.users_integration.get_user", return_value=None),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            authentication_service_refresh_service._replay_rotation(
                "web", _session(), "old-token", "127.0.0.1", "agent", 5, MagicMock(), MagicMock(), mock_db
            )

        self._assert_refused(audit, "failure", "user_not_found")

    def test_a_replay_for_an_inactive_user_is_denied(self, mock_db):
        inactive = SimpleNamespace(id=5, username="alice", active=False, access_type="regular")
        with (
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token",
                return_value=("replacement", datetime(2999, 1, 1, tzinfo=UTC)),
            ),
            patch(f"{_SERVICE}.users_integration.get_user", return_value=inactive),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            authentication_service_refresh_service._replay_rotation(
                "web", _session(), "old-token", "127.0.0.1", "agent", 5, MagicMock(), MagicMock(), mock_db
            )

        self._assert_refused(audit, "denied", "user_inactive")

    def test_a_reuse_keeps_its_own_row_and_writes_no_refresh_row(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
                return_value=(True, False),
            ),
            patch(f"{_SERVICE}.sessions_integration.invalidate_token_family"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _refresh(mock_db, session=_session())

        audit.assert_audited(authentication_audit_actions.REFRESH_TOKEN_REUSE.id, outcome="denied")
        audit.assert_not_audited(_REFRESH)

    def _rotate_losing_the_race(self, db, *, reuse_after_conflict):
        hasher = MagicMock()
        hasher.verify_password.return_value = True
        tokens = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
        integration = "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration"
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(f"{integration}.check_token_reuse", side_effect=[(False, False), reuse_after_conflict]) as check,
            patch(f"{integration}.store_rotated_token", side_effect=core_exceptions.ConflictError("rotated")),
            patch(f"{_SERVICE}.users_integration.get_user", return_value=SimpleNamespace(id=5, active=True)),
            patch("modules.auth.authentication.token_service.create_tokens", return_value=tokens),
            patch(f"{_SERVICE}.sessions_integration.invalidate_token_family") as invalidate,
            patch.object(authentication_service_refresh_service, "_replay_rotation") as replay,
        ):
            try:
                _refresh(db, session=_session(), hasher=hasher)
            finally:
                self.check, self.invalidate, self.replay = check, invalidate, replay

    def test_a_lost_rotation_race_from_another_client_ends_the_family(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._rotate_losing_the_race(mock_db, reuse_after_conflict=(True, False))

        audit.assert_audited(authentication_audit_actions.REFRESH_TOKEN_REUSE.id, outcome="denied")
        self.invalidate.assert_called_once_with("family", mock_db)
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_called_once()
        self.replay.assert_not_called()
        assert self.check.call_args.args == ("old-token", mock_db)
        assert self.check.call_args.kwargs == {"ip_address": "127.0.0.1", "user_agent": "agent"}

    def test_a_lost_rotation_race_from_the_same_client_replays_the_winners_token(self, mock_db):
        with jasil_testing.capture_audit() as audit:
            self._rotate_losing_the_race(mock_db, reuse_after_conflict=(True, True))

        self.invalidate.assert_not_called()
        self.replay.assert_called_once()
        assert self.replay.call_args.args[3:5] == ("127.0.0.1", "agent")
        audit.assert_not_audited(authentication_audit_actions.REFRESH_TOKEN_REUSE.id)

    def test_a_retry_in_the_grace_window_from_another_client_ends_the_family(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
                return_value=(True, False),
            ) as check,
            patch(f"{_SERVICE}.sessions_integration.invalidate_token_family") as invalidate,
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _refresh(mock_db, session=_session())

        audit.assert_audited(authentication_audit_actions.REFRESH_TOKEN_REUSE.id, outcome="denied")
        invalidate.assert_called_once_with("family", mock_db)
        assert check.call_args.kwargs == {"ip_address": "127.0.0.1", "user_agent": "agent"}

    def test_a_retry_in_the_grace_window_from_the_same_client_is_replayed(self, mock_db):
        with (
            patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
                return_value=(True, True),
            ),
            patch(f"{_SERVICE}.sessions_integration.invalidate_token_family") as invalidate,
            patch.object(authentication_service_refresh_service, "_replay_rotation") as replay,
        ):
            _refresh(mock_db, session=_session())

        invalidate.assert_not_called()
        assert replay.call_args.args[3:5] == ("127.0.0.1", "agent")

    def test_a_replay_asks_for_the_replacement_on_behalf_of_the_presenting_client(self, mock_db):
        with (
            patch(
                "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token",
                return_value=None,
            ) as get_replay,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            authentication_service_refresh_service._replay_rotation(
                "web", _session(), "old-token", "127.0.0.1", "agent", 5, MagicMock(), MagicMock(), mock_db
            )

        get_replay.assert_called_once_with("old-token", mock_db, ip_address="127.0.0.1", user_agent="agent")


class TestMfaChallengeRefusal:
    def _verify(self, db, *, pending, claimed):
        store = MagicMock()
        store.get_pending_login.return_value = pending
        store.claim_pending_login.return_value = claimed
        store.is_locked_out.return_value = False
        request = SimpleNamespace(mfa_challenge="challenge-secret", mfa_code="123456")
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=_USER),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=True),
        ):
            authentication_service.verify_mfa_and_login(
                "127.0.0.1",
                "agent",
                request,
                "web",
                MagicMock(),
                store,
                MagicMock(),
                MagicMock(),
                db,
                password_change_store=MagicMock(),
                device_id=None,
            )

    def test_an_expired_challenge_is_a_failure_with_no_target(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._verify(mock_db, pending=None, claimed=None)

        entry = audit.assert_audited(_LOGIN, outcome="failure")
        assert entry.details == {
            "method": "password",
            "mfa": True,
            "reason": "mfa_challenge_expired",
            "new_device": False,
        }
        assert entry.target_id is None
        assert "challenge-secret" not in repr(entry)

    def test_a_challenge_of_the_other_client_type_is_audited_like_an_expired_one(self, mock_db):
        mobile = pending_login(5, auth_constants.ClientType.MOBILE, "c" * 43, "S256")

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._verify(mock_db, pending=mobile, claimed=mobile)

        entry = audit.assert_audited(_LOGIN, outcome="failure")
        assert entry.details["reason"] == "mfa_challenge_expired"
        assert entry.target_id is None

    def test_a_challenge_claimed_by_a_concurrent_request_is_a_failure_that_targets_the_user(self, mock_db):
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.UnauthenticatedError):
            self._verify(mock_db, pending=pending_login(5), claimed=None)

        entry = audit.assert_audited(_LOGIN, outcome="failure", target_type="user", target_id="5", target_owner_id="5")
        assert entry.details == {
            "method": "password",
            "mfa": True,
            "reason": "mfa_challenge_claimed",
            "new_device": False,
        }
        assert len(audit.matching(_LOGIN)) == 1


class TestLockoutAppliedByFailedCodes:
    def test_a_wrong_mfa_code_that_locks_the_account_audits_the_lockout_against_the_user(
        self, mock_db, password_hasher
    ):
        store = MagicMock()
        store.record_failed_attempt.return_value = pending_login_store.FailedMfaRecord(
            count=5, account_locked_now=False
        )
        with (
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=False),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidMfaCodeError),
        ):
            authentication_service.require_valid_mfa_code(
                "alice",
                5,
                login_audit_actions.LoginMethod.PASSWORD,
                "123456",
                store,
                password_hasher,
                mock_db,
            )

        entry = audit.assert_audited(
            "auth.lockout.apply", outcome="success", target_type="user", target_id="5", target_owner_id="5"
        )
        assert entry.details == {"counter": "mfa", "failed_attempts": 5}
        assert "alice" not in repr(entry)

    def test_a_wrong_login_password_that_locks_the_account_audits_the_lockout(self, mock_db):
        failed_attempts = MagicMock(is_locked_out=MagicMock(return_value=False))
        failed_attempts.record_failed_attempt.return_value = failed_login_store.FailedLoginRecord(5, False)
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=None),
            patch(
                f"{_SERVICE}.authenticate_user",
                side_effect=core_exceptions.UnauthenticatedError("no", scheme="Bearer"),
            ),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            authentication_service.login_for_access_token(
                "127.0.0.1",
                "agent",
                "alice",
                "secret",
                "web",
                failed_attempts,
                MagicMock(),
                MagicMock(),
                MagicMock(),
                mock_db,
                code_challenge=None,
                code_challenge_method=None,
                password_change_store=MagicMock(),
                device_id=None,
            )

        entry = audit.assert_audited("auth.lockout.apply", outcome="success")
        assert entry.details == {"counter": "login", "failed_attempts": 5}
        assert entry.target_id is None
