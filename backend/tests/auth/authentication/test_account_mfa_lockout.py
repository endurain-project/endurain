"""An account locked by 100 wrong MFA codes in a row still admits its known devices, and tells its owner."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.providers import StateBackendUnavailableError

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.network as core_network
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.mfa_workflow_service as mfa_workflow
import modules.auth.authentication.event_publishers as authentication_event_publishers
import modules.auth.authentication.events as authentication_events
import modules.auth.authentication.service as authentication_service
import modules.auth.authentication.sso_exchange_service as sso_exchange_service
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.lockout.audit_actions as lockout_audit_actions
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa.schema as mfa_schema
import modules.auth.schema as auth_schema
from tests.auth.authentication.conftest import BACKUP_CODE, USER_ID, USERNAME, WEB

_USER_ID_5 = uuid.UUID(int=5)

IDP_ID = uuid.uuid4()

_SERVICE = "modules.auth.authentication.service"
_SSO = "modules.auth.authentication.sso_exchange_service"
_PUBLISH = "modules.auth.authentication.event_publishers.platform_publisher.publish"
_WRONG = "000000"
_DEVICE_ID = "d" * 43
_LOCK = lockout_audit_actions.LOCKOUT_APPLY.id
_IP = "testclient"
_TIER_KEY = f"{USERNAME}|{_IP}"


def _store() -> pending_login_store.PendingMFALogin:
    return pending_login_store.PendingMFALogin(core_dependencies.get_platform_state())


def _record_account_failures(count: int) -> None:
    """Count wrong codes against the account only, as if earlier challenges had spent them."""
    store = _store()
    for _ in range(count):
        store._by_account.record_failure(str(USER_ID))


def _lock_account() -> None:
    _record_account_failures(lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS[0][0])


def _verify(stack, code, *, device_id=None):
    challenge = stack.client.post(
        "/auth/login", data={"username": USERNAME, "password": "correct horse battery staple"}, headers=WEB
    ).json()["mfa_challenge"]
    headers = WEB | ({"X-Device-Id": device_id} if device_id else {})
    return stack.client.post("/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": code}, headers=headers)


def _mfa_locked_events(publish: MagicMock) -> list:
    return [c for c in publish.call_args_list if c.args[0] == authentication_events.MFA_LOCKED]


def _verify_from(stack, ip, code):
    """Sign in with the password and verify the code, both from the client address ``ip``."""
    with patch.object(core_network, "get_ip_address", return_value=ip):
        return _verify(stack, code)


class TestTieredLockIsPerNetwork:
    def test_wrong_codes_from_one_network_do_not_stop_a_correct_code_from_another(self, mfa_plain_signin):
        for _ in range(5):
            assert _verify_from(mfa_plain_signin, "203.0.113.5", _WRONG).status_code == 400
        assert _verify_from(mfa_plain_signin, "203.0.113.5", BACKUP_CODE).status_code == 429

        assert _verify_from(mfa_plain_signin, "198.51.100.9", BACKUP_CODE).status_code == 200

    def test_the_account_wide_lock_still_holds_across_networks(self, mfa_plain_signin):
        _lock_account()

        assert _verify_from(mfa_plain_signin, "198.51.100.9", BACKUP_CODE).status_code == 429


class TestHundredthWrongCode:
    def test_it_locks_audits_once_and_tells_the_owner_once(self, mfa_plain_signin):
        _record_account_failures(99)

        with patch(_PUBLISH) as publish, jasil_testing.capture_audit() as audit:
            response = _verify(mfa_plain_signin, _WRONG)

        assert response.status_code == 400
        rows = [r for r in audit.matching(_LOCK) if r.details["counter"] == "mfa_account"]
        assert len(rows) == 1
        assert rows[0].details == {"counter": "mfa_account", "failed_attempts": 100}
        assert (rows[0].outcome, rows[0].target_type, rows[0].target_id, rows[0].target_owner_id) == (
            "success",
            "user",
            str(USER_ID),
            str(USER_ID),
        )
        assert USERNAME not in repr(rows[0])
        events = _mfa_locked_events(publish)
        assert len(events) == 1
        assert events[0].args[1] == {"user_id": str(USER_ID)}
        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is True

    def test_the_ninety_ninth_wrong_code_locks_nothing_and_tells_nobody(self, mfa_plain_signin):
        _record_account_failures(98)

        with patch(_PUBLISH) as publish, jasil_testing.capture_audit() as audit:
            response = _verify(mfa_plain_signin, _WRONG)

        assert response.status_code == 400
        assert [r for r in audit.matching(_LOCK) if r.details["counter"] == "mfa_account"] == []
        assert _mfa_locked_events(publish) == []
        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False

    def test_the_exchange_records_the_second_factor_it_verified(self, mfa_plain_signin):
        claims = []

        refusal = _exchange(mfa_plain_signin, _store(), claims=claims)

        assert refusal is None
        assert claims[0][3] == ["fed", "otp", "mfa"]

    def test_wrong_codes_across_many_challenges_reach_the_cap(self, mfa_plain_signin):
        store = _store()
        for _ in range(100):
            store.record_failed_attempt(USERNAME, _IP, user_id=USER_ID)
            store._lockout.reset_attempts(_TIER_KEY)

        assert store.is_locked_out(USERNAME, _IP, user_id=USER_ID) is True

    def test_a_known_device_that_gets_the_code_wrong_still_counts_toward_the_cap(self, mfa_plain_signin):
        _record_account_failures(99)

        with (
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True),
            patch(_PUBLISH) as publish,
        ):
            response = _verify(mfa_plain_signin, _WRONG, device_id=_DEVICE_ID)

        assert response.status_code == 400
        assert len(_mfa_locked_events(publish)) == 1
        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is True

    def test_a_wrong_code_while_locked_does_not_tell_again(self, mfa_plain_signin):
        _lock_account()

        with (
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True),
            patch(_PUBLISH) as publish,
            jasil_testing.capture_audit() as audit,
        ):
            response = _verify(mfa_plain_signin, _WRONG, device_id=_DEVICE_ID)

        assert response.status_code == 400
        assert _mfa_locked_events(publish) == []
        assert [r for r in audit.matching(_LOCK) if r.details["counter"] == "mfa_account"] == []


class TestLockedAccount:
    def test_an_unknown_device_is_refused_even_with_a_correct_code(self, mfa_plain_signin):
        _lock_account()

        with jasil_testing.capture_audit() as audit:
            response = _verify(mfa_plain_signin, BACKUP_CODE)

        assert response.status_code == 429
        entry = audit.assert_audited("auth.session.login", outcome="denied", target_type="user", target_id=str(USER_ID))
        assert entry.details["reason"] == "locked_out"
        assert entry.details["mfa"] is True

    def test_a_device_the_account_never_used_is_refused(self, mfa_plain_signin):
        _lock_account()

        with patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=False) as known:
            response = _verify(mfa_plain_signin, BACKUP_CODE, device_id=_DEVICE_ID)

        assert response.status_code == 429
        known.assert_called_once()
        assert known.call_args.args[:2] == (USER_ID, _DEVICE_ID)

    def test_a_known_device_completes_with_a_correct_code_and_lifts_the_lock(self, mfa_plain_signin):
        _lock_account()

        with patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True) as known:
            response = _verify(mfa_plain_signin, BACKUP_CODE, device_id=_DEVICE_ID)

        assert response.status_code == 200
        assert known.call_args.args[:2] == (USER_ID, _DEVICE_ID)
        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False

    def test_a_known_device_is_still_held_by_the_tiered_lock(self, mfa_plain_signin):
        store = _store()
        for _ in range(5):
            store._lockout.record_failure(_TIER_KEY)

        with patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True):
            response = _verify(mfa_plain_signin, BACKUP_CODE, device_id=_DEVICE_ID)

        assert response.status_code == 429

    def test_a_client_without_a_device_id_is_refused_without_a_lookup(self, mfa_plain_signin):
        _lock_account()

        with patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=False) as known:
            response = _verify(mfa_plain_signin, BACKUP_CODE)

        assert response.status_code == 429
        assert known.call_args.args[1] is None

    def test_a_success_forgets_the_account_count(self, mfa_plain_signin):
        _record_account_failures(99)

        assert _verify(mfa_plain_signin, BACKUP_CODE).status_code == 200

        with patch(_PUBLISH) as publish:
            assert _verify(mfa_plain_signin, _WRONG).status_code == 400
        assert _mfa_locked_events(publish) == []
        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False


def _exchange(stack, store, *, device_id=None, code=BACKUP_CODE, claims=None):
    """Run the SSO token exchange for the account with MFA, returning the refusal if there was one.

    Each session claim the exchange makes is appended to ``claims``, when given.
    """
    oauth_state = SimpleNamespace(
        id="state",
        purpose="login",
        code_challenge="c",
        code_challenge_method="S256",
        client_type="web",
        idp_id=IDP_ID,
        security_generation=0,
    )
    session = SimpleNamespace(
        user_id=USER_ID,
        tokens_exchanged=False,
        expires_at=datetime(2999, 1, 1, tzinfo=UTC),
        client_type="web",
        amr=["fed"],
    )
    tokens = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")
    with (
        patch(f"{_SSO}.sessions_integration.get_session_with_oauth_state", return_value=(session, oauth_state)),
        patch(f"{_SSO}.auth_computation.validate_pkce_verifier"),
        patch(f"{_SSO}.server_settings_integration.get_session_policy"),
        patch(f"{_SSO}.authentication_token_service.create_tokens", return_value=tokens),
        patch(
            f"{_SSO}.sessions_integration.claim_session_for_token_exchange",
            side_effect=lambda *args: (
                (claims.append(args) if claims is not None else None) or datetime(2999, 1, 1, tzinfo=UTC)
            ),
        ),
        patch(
            f"{_SSO}.known_devices_integration.record_sign_in",
            return_value=MagicMock(device_id="d" * 43, new_device=False),
        ),
        patch(f"{_SSO}.authentication_token_service.build_web_token_response"),
        stack.factory() as db,
    ):
        try:
            sso_exchange_service.exchange_tokens_for_session(
                "sid",
                "verifier",
                code,
                "web",
                "127.0.0.1",
                "agent",
                store,
                credentials_integration.get_password_hasher(),
                MagicMock(),
                db,
                device_id=device_id,
            )
        except core_exceptions.DomainError as err:
            return err
    return None


class TestSsoExchange:
    def test_an_unknown_device_is_refused_by_the_account_lock(self, mfa_plain_signin):
        _lock_account()

        assert isinstance(_exchange(mfa_plain_signin, _store()), core_exceptions.TooManyRequestsError)

    def test_a_known_device_completes_the_exchange_and_lifts_the_lock(self, mfa_plain_signin):
        _lock_account()

        with patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True) as known:
            refusal = _exchange(mfa_plain_signin, _store(), device_id=_DEVICE_ID)

        assert refusal is None
        assert known.call_args.args[:2] == (USER_ID, _DEVICE_ID)
        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False

    def test_the_hundredth_wrong_code_locks_and_tells_the_owner_once(self, mfa_plain_signin):
        _record_account_failures(99)

        with patch(_PUBLISH) as publish, jasil_testing.capture_audit() as audit:
            refusal = _exchange(mfa_plain_signin, _store(), code=_WRONG)

        assert isinstance(refusal, core_exceptions.InvalidMfaCodeError)
        assert len(_mfa_locked_events(publish)) == 1
        rows = [r for r in audit.matching(_LOCK) if r.details["counter"] == "mfa_account"]
        assert [r.details for r in rows] == [{"counter": "mfa_account", "failed_attempts": 100}]


def test_the_event_names_the_user_and_nothing_else(mock_db):
    with patch(_PUBLISH) as publish:
        authentication_event_publishers.publish_mfa_locked(_USER_ID_5, mock_db)

    event_type, payload = publish.call_args.args
    assert event_type == authentication_events.MFA_LOCKED == "auth.mfa_locked"
    assert payload == {"user_id": str(_USER_ID_5)}
    assert publish.call_args.kwargs["db"] is mock_db
    assert publish.call_args.kwargs["schema_version"] == 1


def test_the_lock_lasts_thirty_days_after_one_hundred_wrong_codes():
    assert lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS == ((100, 30 * 24 * 60 * 60, "30 days"),)
    assert lockout_contracts.ACCOUNT_MFA_ATTEMPTS_TTL_SECONDS == 30 * 24 * 60 * 60
    assert lockout_contracts.MFA_LOCKOUT_TIERS == ((5, 300, "5 min"), (10, 1800, "30 min"), (15, 7200, "2 hours"))


class TestLiftingTheLock:
    def test_turning_mfa_on_lifts_it(self, mfa_plain_signin):
        _lock_account()
        request = mfa_schema.MFASetupRequest(
            totp_code="123456",
            step_up=auth_schema.StepUpVerification(current_password="pw"),
            revoke_other_sessions=False,
        )
        secrets = MagicMock()
        secrets.get_secret.return_value = "secret"
        with (
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.mfa_integration, "enable_user_mfa", return_value=["a"]),
            patch.object(mfa_workflow.account_security_event_publishers, "publish_account_security_changed"),
            mfa_plain_signin.factory() as db,
        ):
            mfa_workflow.enable_mfa(request, USER_ID, "sid", MagicMock(), secrets, db)

        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False

    def test_turning_mfa_off_lifts_it(self, mfa_plain_signin):
        _lock_account()
        with (
            patch.object(mfa_workflow.step_up_service, "verify_step_up_credentials"),
            patch.object(mfa_workflow.account_security_event_publishers, "publish_account_security_changed"),
            mfa_plain_signin.factory() as db,
        ):
            mfa_workflow.disable_mfa(
                auth_schema.StepUpVerification(current_password="pw", mfa_code="123456"),
                USER_ID,
                "sid",
                MagicMock(),
                db,
                revoke_other_sessions=False,
            )

        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False

    def test_an_administrator_resetting_mfa_lifts_it(self, mfa_plain_signin):
        _lock_account()
        with mfa_plain_signin.factory() as db:
            account_security_service.reset_managed_user_mfa(USER_ID, db)
            db.commit()

        assert _store().is_locked_out(USERNAME, _IP, user_id=USER_ID) is False

    def test_the_count_is_cleared_too(self, mfa_plain_signin):
        _record_account_failures(99)
        with mfa_plain_signin.factory() as db:
            account_security_service.reset_managed_user_mfa(USER_ID, db)
            db.commit()

        assert _store().record_failed_attempt(USERNAME, _IP, user_id=USER_ID).account_locked_now is False

    def test_the_username_is_matched_regardless_of_case(self):
        state = core_dependencies.get_platform_state()
        store = pending_login_store.PendingMFALogin(state)
        for _ in range(100):
            store.record_failed_attempt("Alice", _IP, user_id=USER_ID)
        store._lockout.reset_attempts(f"alice|{_IP}")

        mfa_integration.clear_mfa_account_lockout(USER_ID)

        assert store.is_locked_out("Alice", _IP, user_id=USER_ID) is False

    def test_a_state_outage_does_not_fail_the_clear(self):
        state = MagicMock()
        state.delete.side_effect = StateBackendUnavailableError("down")

        with patch("modules.auth.mfa.integration_service.core_dependencies.get_platform_state", return_value=state):
            mfa_integration.clear_mfa_account_lockout(USER_ID)

    def test_a_state_outage_does_not_fail_an_administrator_reset(self, mfa_plain_signin):
        state = MagicMock()
        state.delete.side_effect = StateBackendUnavailableError("down")

        with (
            patch("modules.auth.mfa.integration_service.core_dependencies.get_platform_state", return_value=state),
            mfa_plain_signin.factory() as db,
        ):
            account_security_service.reset_managed_user_mfa(USER_ID, db)
            db.commit()

        with mfa_plain_signin.factory() as db:
            assert mfa_integration.is_mfa_enabled_for_user(USER_ID, db) is False


@pytest.mark.parametrize("device_id", [_DEVICE_ID, None])
def test_a_store_outage_while_checking_the_lock_answers_503(device_id):
    state = MagicMock()
    state.get.side_effect = StateBackendUnavailableError("down")
    store = pending_login_store.PendingMFALogin(state)

    with pytest.raises(core_exceptions.ServiceUnavailableError):
        authentication_service.refuse_while_mfa_locked_out(
            USERNAME, _IP, USER_ID, login_audit_actions.LoginMethod.PASSWORD, store, device_id, MagicMock()
        )
