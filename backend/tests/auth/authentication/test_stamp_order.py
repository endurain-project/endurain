"""A sign-in proof is stamped with the generation read before its credential was verified, and a lookup of a deleted
user precedes the generation lock."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.login_audit.audit_actions as login_audit_actions
from tests._helpers.auth import pending_login

_USER_ID = uuid.UUID(int=5)

_SERVICE = "modules.auth.authentication.service"
_USER = SimpleNamespace(id=_USER_ID, username="alice", active=True, access_type="regular")
_NO_LOCK = failed_login_store.FailedLoginRecord(client_count=1, account_locked_now=False)
_CHALLENGE = "a" * 43


@pytest.fixture(autouse=True)
def _known_device():
    record = known_devices_contracts.SignInRecord(device_id="d" * 43, new_device=False)
    with patch(f"{_SERVICE}.known_devices_integration.record_sign_in", return_value=record):
        yield


def _login(db, *, pending_mfa_store=None, password_change_store=None, client_type="web", **kwargs):
    kwargs = {"code_challenge": None, "code_challenge_method": None, **kwargs}
    return authentication_service.login_for_access_token(
        "127.0.0.1",
        "agent",
        "alice",
        "secret",
        client_type,
        MagicMock(is_locked_out=MagicMock(return_value=False), record_failed_attempt=MagicMock(return_value=_NO_LOCK)),
        pending_mfa_store or MagicMock(),
        MagicMock(),
        MagicMock(),
        db,
        password_change_store=password_change_store or MagicMock(),
        device_id=None,
        **kwargs,
    )


class TestLoginReadsTheStampBeforeTheCredential:
    """A security change that commits while the password is verified must outdate the proof the sign-in creates."""

    @pytest.fixture
    def reset_during_the_hash(self, security_generations, mock_db):
        """Order the generation read against the password check; the check moves the generation as a reset would."""
        order = MagicMock()
        security_generations.generations[_USER_ID] = 4

        def read(user_id, db):
            order.read_generation()
            return security_generations.generations.get(user_id, 0)

        def verify(*args, **kwargs):
            order.authenticate_user()
            security_generations.stage_bump(_USER_ID, mock_db)
            return _USER

        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.security_generation_integration.current_generation", side_effect=read),
            patch(f"{_SERVICE}.authenticate_user", side_effect=verify),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
        ):
            yield order

    @staticmethod
    def _names(order):
        return [call[0] for call in order.mock_calls]

    def test_the_mfa_challenge_carries_the_generation_read_before_the_password_check(
        self, reset_during_the_hash, mock_db
    ):
        store = MagicMock(add_pending_login=MagicMock(return_value="challenge"))
        with patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=True):
            _login(mock_db, pending_mfa_store=store)

        assert self._names(reset_during_the_hash) == ["read_generation", "authenticate_user"]
        assert store.add_pending_login.call_args.args[0].security_generation == 4

    def test_the_forced_change_challenge_carries_the_generation_read_before_the_password_check(
        self, reset_during_the_hash, mock_db
    ):
        store = MagicMock(add=MagicMock(return_value="challenge"))
        with (
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=True),
        ):
            _login(mock_db, password_change_store=store)

        assert self._names(reset_during_the_hash) == ["read_generation", "authenticate_user"]
        assert store.add.call_args.args[0].security_generation == 4

    def test_the_mobile_state_carries_the_generation_read_before_the_password_check(
        self, reset_during_the_hash, mock_db
    ):
        with (
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(f"{_SERVICE}.create_mobile_pkce_session_response") as pkce,
        ):
            _login(mock_db, client_type="mobile", code_challenge=_CHALLENGE, code_challenge_method="S256")

        assert self._names(reset_during_the_hash) == ["read_generation", "authenticate_user"]
        assert pkce.call_args.kwargs["security_generation"] == 4


class TestWebSignInChecksTheStamp:
    """A web session is created only when the account's generation is still the one the sign-in's proof carries."""

    @staticmethod
    def _complete(db, security_generation, hasher=None, token_manager=None):
        return authentication_service.complete_login(
            "127.0.0.1",
            "agent",
            _USER,
            hasher or MagicMock(),
            token_manager or MagicMock(),
            db,
            mfa=False,
            security_generation=security_generation,
            device_hash=None,
        )

    @pytest.mark.parametrize("stamp", [3, None])
    def test_a_stale_or_missing_stamp_creates_no_session_and_is_refused_like_a_wrong_password(
        self, mock_db, security_generations, stamp
    ):
        security_generations.generations[_USER_ID] = 4
        with (
            patch(f"{_SERVICE}.authentication_token_service.create_tokens") as create_tokens,
            patch(f"{_SERVICE}.sessions_integration.create_session") as create_session,
            patch(f"{_SERVICE}.login_audit_integration.record_login_refusal") as refusal,
            pytest.raises(
                core_exceptions.UnauthenticatedError, match="Unable to authenticate with provided credentials"
            ),
        ):
            self._complete(mock_db, stamp)

        create_tokens.assert_not_called()
        create_session.assert_not_called()
        mock_db.commit.assert_not_called()
        refusal.assert_called_once()
        assert refusal.call_args.args[2] == login_audit_actions.LoginFailureReason.SECURITY_CHANGED
        assert refusal.call_args.kwargs["user_id"] == _USER_ID

    def test_the_current_stamp_creates_the_session(self, mock_db, security_generations):
        security_generations.generations[_USER_ID] = 4
        with (
            patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
            patch(f"{_SERVICE}.authentication_token_service.create_tokens", return_value=tuple(range(6))),
            patch(f"{_SERVICE}.authentication_token_service.build_web_token_response"),
            patch(f"{_SERVICE}.sessions_integration.create_session") as create_session,
        ):
            self._complete(mock_db, 4)

        create_session.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_a_reset_that_commits_during_the_hash_leaves_a_web_sign_in_without_a_session(
        self, mock_db, security_generations
    ):
        security_generations.generations[_USER_ID] = 4

        def verify(*args, **kwargs):
            security_generations.stage_bump(_USER_ID, mock_db)
            return _USER

        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.authenticate_user", side_effect=verify),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(f"{_SERVICE}.login_audit_integration.record_login_refusal"),
            patch(f"{_SERVICE}.sessions_integration.create_session") as create_session,
            pytest.raises(core_exceptions.UnauthenticatedError, match="Unable to authenticate"),
        ):
            _login(mock_db)

        create_session.assert_not_called()

    def test_the_stamp_read_before_the_password_check_reaches_the_web_session(self, mock_db, security_generations):
        security_generations.generations[_USER_ID] = 4
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(f"{_SERVICE}.complete_login") as complete,
        ):
            _login(mock_db)

        assert complete.call_args.kwargs["security_generation"] == 4

    def test_the_mfa_challenges_stamp_reaches_the_web_session(self, mock_db, security_generations):
        security_generations.generations[_USER_ID] = 9
        store = MagicMock()
        pending = pending_login(_USER_ID, security_generation=9)
        store.get_pending_login.return_value = pending
        store.claim_pending_login.return_value = pending
        store.is_locked_out.return_value = False
        request = SimpleNamespace(mfa_challenge="challenge", mfa_code="123456")
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=_USER),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=True),
            patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
            patch(f"{_SERVICE}.complete_login") as complete,
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
                mock_db,
                password_change_store=MagicMock(),
                device_id=None,
            )

        assert complete.call_args.kwargs["security_generation"] == 9


class TestMfaStepCarriesTheChallengesStamp:
    """After the MFA step, the forced-change challenge and the mobile state keep the challenge's own stamp."""

    @staticmethod
    def _verify(db, security_generations, *, password_change_required, client_type):
        security_generations.generations[_USER_ID] = 9
        store = MagicMock()
        challenge_type = auth_constants.ClientType(client_type)
        pending = pending_login(_USER_ID, client_type=challenge_type, security_generation=9)
        pending = pending.model_copy(
            update={"code_challenge": _CHALLENGE, "code_challenge_method": "S256"} if client_type == "mobile" else {}
        )
        store.get_pending_login.return_value = pending
        store.claim_pending_login.return_value = pending
        store.is_locked_out.return_value = False
        password_change_store = MagicMock(add=MagicMock(return_value="challenge"))
        request = SimpleNamespace(mfa_challenge="challenge", mfa_code="123456")
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=_USER),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=True),
            patch(
                f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=password_change_required
            ),
            # A fresh read would return this value instead of the challenge's.
            patch(f"{_SERVICE}.security_generation_integration.current_generation", return_value=77),
            patch(f"{_SERVICE}.create_mobile_pkce_session_response") as pkce,
        ):
            authentication_service.verify_mfa_and_login(
                "127.0.0.1",
                "agent",
                request,
                client_type,
                MagicMock(),
                store,
                MagicMock(),
                MagicMock(),
                db,
                password_change_store=password_change_store,
                device_id=None,
            )
        return password_change_store, pkce

    def test_the_forced_change_challenge_is_stamped_with_the_mfa_challenges_generation(
        self, mock_db, security_generations
    ):
        password_change_store, _ = self._verify(
            mock_db, security_generations, password_change_required=True, client_type="web"
        )

        assert password_change_store.add.call_args.args[0].security_generation == 9

    def test_the_mobile_state_is_stamped_with_the_mfa_challenges_generation(self, mock_db, security_generations):
        _, pkce = self._verify(mock_db, security_generations, password_change_required=False, client_type="mobile")

        assert pkce.call_args.kwargs["security_generation"] == 9


class TestMfaStepOfADeletedUser:
    def test_a_deleted_user_is_refused_without_locking_the_generation(self, mock_db):
        store = MagicMock()
        store.get_pending_login.return_value = pending_login(_USER_ID)
        request = SimpleNamespace(mfa_challenge="challenge", mfa_code="123456")
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=None),
            patch(f"{_SERVICE}.security_generation_integration.matches_locked") as matches_locked,
            pytest.raises(core_exceptions.UnauthenticatedError, match="Unable to authenticate"),
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
                mock_db,
                password_change_store=MagicMock(),
                device_id=None,
            )

        matches_locked.assert_not_called()
        store.record_failed_attempt.assert_not_called()
