"""A sensitive request re-proves identity: password, TOTP or backup code, or a fresh identity-provider sign-in.

The route under test is ``POST /profile/api-keys``; every step-up route shares the check.
"""

import time
import uuid

import jasil.backends.state_memory as state_memory
import jasil.runtime as jasil_runtime
import pytest

import core.config as core_config
import core.exceptions as core_exceptions
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
from tests._factories.account_security import deliver_notices, sent_to, session_ids, step_up_proof
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.tokens import audit_rows, make_mfa, totp_code
from tests._factories.users import PASSWORD, audit_rows_of, make_user

_API_KEYS = f"{core_config.ROOT_PATH}/profile/api-keys"
_ACTION = identity_providers_constants.StepUpAction.API_KEY_CREATE
_STEP_UP_FAILED = "urn:endurain:error:step-up-failed"
_LAST_TIER = lockout_contracts.STEP_UP_LOCKOUT_TIERS[-1][0]


@pytest.fixture
def elapse(monkeypatch):
    """Return a function that moves the in-memory state's clock forward, so a lock's time passes without waiting."""
    offset = [0.0]
    real = time.monotonic

    class _Time:
        def __getattr__(self, name):
            return getattr(time, name)

        @staticmethod
        def monotonic() -> float:
            return real() + offset[0]

    monkeypatch.setattr(state_memory, "time", _Time())

    def advance(seconds: float) -> None:
        offset[0] += seconds

    return advance


def _create_key(signed_in, step_up: dict):
    return signed_in.client.post(_API_KEYS, json={"name": "key", "scopes": ["account"], "step_up": step_up})


def _store() -> step_up_store.StepUpAttempts:
    return step_up_store.StepUpAttempts(jasil_runtime.get_active_platform().state)


def _session_key(signed_in) -> str:
    return f"user:{signed_in.user.id}:session:{signed_in.session_id}"


def _failures(signed_in) -> int:
    """Return the failures recorded for the session so far (the read records one more)."""
    return _store().record_failed_attempt(_session_key(signed_in)) - 1


def _refusals(committed_sessions) -> list[tuple[str, str, str]]:
    rows = audit_rows(committed_sessions, login_audit_actions.STEP_UP_VERIFY)
    return [(row.outcome, row.details["method"], row.details["reason"]) for row in rows]


def _local_user(committed_sessions, sign_in, **fields):
    with committed_sessions() as db:
        user = make_user(db, **fields)
        db.commit()
    return sign_in(user)


class TestPassword:
    def test_the_current_password_authorises_the_request(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)

        response = _create_key(owner, {"current_password": PASSWORD})

        assert response.status_code == 201
        assert _refusals(committed_sessions) == []

    @pytest.mark.parametrize("step_up", [{"current_password": "not-the-password"}, {}], ids=["wrong", "missing"])
    def test_a_wrong_or_missing_password_is_refused_with_the_one_answer_and_audited(
        self, committed_sessions, sign_in, step_up
    ):
        owner = _local_user(committed_sessions, sign_in)

        response = _create_key(owner, step_up)

        assert response.status_code == 403
        assert response.json()["type"] == _STEP_UP_FAILED
        assert "WWW-Authenticate" not in response.headers
        assert _refusals(committed_sessions) == [("failure", "password", "invalid_credentials")]
        assert _failures(owner) == 1

    def test_a_correct_password_resets_the_session_count(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)
        _create_key(owner, {"current_password": "wrong"})
        _create_key(owner, {"current_password": "wrong"})

        assert _create_key(owner, {"current_password": PASSWORD}).status_code == 201

        assert _failures(owner) == 0

    def test_a_decomposed_password_matches_a_composed_hash(self, committed_sessions, sign_in):
        composed, decomposed = "café-au-lait-noir", "café-au-lait-noir"
        owner = _local_user(committed_sessions, sign_in)
        with committed_sessions() as db:
            hashed = credentials_integration.get_password_hasher().hash_password(composed)
            credentials_integration.set_local_password_hash(owner.user.id, hashed, db, change_required=False)
            db.commit()

        assert _create_key(owner, {"current_password": decomposed}).status_code == 201

    def test_a_hash_of_the_raw_non_nfc_text_is_refused(self, committed_sessions, sign_in):
        decomposed = "café-au-lait-noir"
        owner = _local_user(committed_sessions, sign_in)
        with committed_sessions() as db:
            hashed = credentials_integration.get_password_hasher().hash_password(decomposed)
            credentials_integration.set_local_password_hash(owner.user.id, hashed, db, change_required=False)
            db.commit()

        assert _create_key(owner, {"current_password": decomposed}).status_code == 403

    def test_a_legacy_hash_fails_like_a_wrong_password(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)
        legacy = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5lC7Zq3o1m1u0YF1kXJq8r9eJ8q7y6e"
        with committed_sessions() as db:
            credentials_integration.set_local_password_hash(owner.user.id, legacy, db, change_required=False)
            db.commit()

        response = _create_key(owner, {"current_password": "x" * 100})

        assert response.status_code == 403
        assert response.json()["type"] == _STEP_UP_FAILED


class TestSecondFactor:
    def _mfa_owner(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db)
            factors = make_mfa(db, user)
            db.commit()
        return sign_in(user), factors

    def test_the_password_and_a_current_code_authorise_the_request(self, committed_sessions, sign_in):
        owner, factors = self._mfa_owner(committed_sessions, sign_in)

        response = _create_key(
            owner, {"current_password": PASSWORD, "mfa_code": totp_code(factors.secret, steps_ahead=1)}
        )

        assert response.status_code == 201

    @pytest.mark.parametrize("code", [None, "000000"], ids=["missing", "wrong"])
    def test_a_missing_or_wrong_code_is_refused_like_a_wrong_password(self, committed_sessions, sign_in, code):
        owner, _ = self._mfa_owner(committed_sessions, sign_in)
        step_up = {"current_password": PASSWORD} | ({"mfa_code": code} if code else {})

        response = _create_key(owner, step_up)

        assert response.status_code == 403
        assert response.json()["type"] == _STEP_UP_FAILED
        assert _refusals(committed_sessions) == [("failure", "mfa_code", "invalid_credentials")]

    def test_a_code_works_once(self, committed_sessions, sign_in):
        owner, factors = self._mfa_owner(committed_sessions, sign_in)
        step_up = {"current_password": PASSWORD, "mfa_code": totp_code(factors.secret, steps_ahead=1)}

        first = _create_key(owner, step_up)
        replay = _create_key(owner, step_up)

        assert (first.status_code, replay.status_code) == (201, 403)

    def test_a_backup_code_authorises_the_request_once_and_is_consumed(self, committed_sessions, sign_in):
        owner, factors = self._mfa_owner(committed_sessions, sign_in)
        step_up = {"current_password": PASSWORD, "mfa_code": factors.backup_codes[0]}

        first = _create_key(owner, step_up)
        reused = _create_key(owner, step_up)

        assert (first.status_code, reused.status_code) == (201, 403)
        status = owner.client.get(f"{core_config.ROOT_PATH}/profile/mfa/backup-codes/status").json()
        assert (status["total"], status["unused"], status["used"]) == (10, 9, 1)

    def test_a_backup_code_sends_the_owner_a_notice_with_the_codes_left(self, committed_sessions, sign_in):
        deliver_notices()
        owner, factors = self._mfa_owner(committed_sessions, sign_in)

        _create_key(owner, {"current_password": PASSWORD, "mfa_code": factors.backup_codes[0]})

        (notice,) = [m for m in sent_to(owner.user.email) if "backup code was used" in m.subject]
        assert "9" in notice.text


class TestLockout:
    def _fail(self, owner, times: int):
        return [_create_key(owner, {"current_password": "wrong"}) for _ in range(times)]

    def test_the_fifth_failure_locks_the_session_and_even_the_right_password_waits(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)

        self._fail(owner, 5)
        locked = _create_key(owner, {"current_password": PASSWORD})

        assert locked.status_code == 429
        assert int(locked.headers["Retry-After"]) > 0
        assert _refusals(committed_sessions)[-1] == ("denied", "unspecified", "locked_out")

    def test_the_lock_lifts_when_its_time_has_passed(self, committed_sessions, sign_in, elapse):
        owner = _local_user(committed_sessions, sign_in)
        self._fail(owner, 5)
        assert _create_key(owner, {"current_password": PASSWORD}).status_code == 429

        elapse(6 * 60)

        assert _create_key(owner, {"current_password": PASSWORD}).status_code == 201

    def test_one_session_failing_does_not_lock_the_users_other_session(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)
        other_session = sign_in(owner.user)
        self._fail(owner, 5)

        assert _create_key(owner, {"current_password": PASSWORD}).status_code == 429
        assert _create_key(other_session, {"current_password": PASSWORD}).status_code == 201

    def test_another_users_session_is_not_locked(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)
        stranger = _local_user(committed_sessions, sign_in)
        self._fail(owner, 5)

        assert _create_key(stranger, {"current_password": PASSWORD}).status_code == 201

    def test_the_last_tier_ends_the_session_audits_it_and_tells_the_owner(self, committed_sessions, sign_in, elapse):
        deliver_notices()
        owner = _local_user(committed_sessions, sign_in)
        survivor = sign_in(owner.user)
        store = _store()
        for _ in range(_LAST_TIER - 1):
            store.record_failed_attempt(_session_key(owner))
            elapse(3 * 3600)

        response = _create_key(owner, {"current_password": "wrong"})

        assert response.status_code == 403
        assert session_ids(committed_sessions, owner.user.id) == {survivor.session_id}
        (row,) = audit_rows(committed_sessions, account_security_audit_actions.STEP_UP_SESSION_END)
        assert (row.target_id, row.details["sessions_revoked"]) == (str(owner.user.id), 1)
        assert owner.client.get(f"{core_config.ROOT_PATH}/profile/sessions").status_code == 401
        assert len(sent_to(owner.user.email)) == 1

    def test_the_hundredth_failure_across_sessions_locks_step_up_for_the_account(self, committed_sessions, sign_in):
        deliver_notices()
        owner = _local_user(committed_sessions, sign_in)
        other_session = sign_in(owner.user)
        store = _store()
        cap = lockout_contracts.ACCOUNT_STEP_UP_LOCKOUT_TIERS[0][0]
        for _ in range(cap - 1):
            store.record_account_failure(owner.user.id)

        refused = _create_key(owner, {"current_password": "wrong"})
        locked = _create_key(other_session, {"current_password": PASSWORD})

        assert refused.status_code == 403
        assert locked.status_code == 429
        assert int(locked.headers["Retry-After"]) > 24 * 60 * 60
        assert len(sent_to(owner.user.email)) == 1

    def test_a_successful_step_up_clears_the_account_count(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)
        store = _store()
        for _ in range(50):
            store.record_account_failure(owner.user.id)

        assert _create_key(owner, {"current_password": PASSWORD}).status_code == 201

        assert not any(store.record_account_failure(owner.user.id) for _ in range(60))


class TestIdentityProviderSignIn:
    def _account(self, committed_sessions, sign_in):
        with committed_sessions() as db:
            user = make_user(db, with_password=False)
            idp_id = make_identity_provider(db, f"idp-{uuid.uuid4().hex[:8]}")
            make_identity_link(db, user.id, idp_id, "subject-1")
            db.commit()
        return sign_in(user), idp_id

    def _proof(self, committed_sessions, owner, idp_id, **overrides):
        with committed_sessions() as db:
            return step_up_proof(db, owner.user, overrides.pop("session_id", owner.session_id), idp_id, **overrides)

    def test_a_request_without_proof_is_challenged_and_not_counted(self, committed_sessions, sign_in):
        owner, _ = self._account(committed_sessions, sign_in)

        response = _create_key(owner, {})

        assert response.status_code == 401
        assert response.json()["type"] == "urn:endurain:error:idp-reauth-required"
        assert response.headers["WWW-Authenticate"] == ('Bearer error="insufficient_user_authentication", max_age="60"')
        assert _failures(owner) == 0

    def test_a_fresh_ticket_authorises_the_request_once(self, committed_sessions, sign_in):
        owner, idp_id = self._account(committed_sessions, sign_in)
        proof = self._proof(committed_sessions, owner, idp_id, action=_ACTION)

        first = _create_key(owner, {"idp_reauth": proof})
        again = _create_key(owner, {"idp_reauth": proof})

        assert (first.status_code, again.status_code) == (201, 403)

    @pytest.mark.parametrize("case", ["another-action", "another-session", "wrong-verifier", "another-user"])
    def test_a_ticket_that_does_not_match_is_refused_and_counted(self, committed_sessions, sign_in, case):
        owner, idp_id = self._account(committed_sessions, sign_in)
        other_session = sign_in(owner.user)
        stranger = _local_user(committed_sessions, sign_in)
        overrides = {
            "another-action": {"action": identity_providers_constants.StepUpAction.ACCOUNT_DELETE},
            "another-session": {"action": _ACTION, "session_id": other_session.session_id},
            "wrong-verifier": {"action": _ACTION, "verifier": "w" * 43},
        }.get(case)
        if case == "another-user":
            with committed_sessions() as db:
                proof = step_up_proof(db, stranger.user, owner.session_id, idp_id, action=_ACTION)
        else:
            proof = self._proof(committed_sessions, owner, idp_id, **overrides)

        response = _create_key(owner, {"idp_reauth": proof})

        assert response.status_code == 403
        assert response.json()["type"] == _STEP_UP_FAILED
        assert _refusals(committed_sessions) == [("failure", "identity_provider", "invalid_credentials")]
        assert _failures(owner) == 1

    def test_a_ticket_from_before_a_security_change_pays_for_nothing(self, committed_sessions, sign_in):
        owner, idp_id = self._account(committed_sessions, sign_in)
        proof = self._proof(committed_sessions, owner, idp_id, action=_ACTION)
        with committed_sessions() as db:
            security_generation_integration.stage_bump(owner.user.id, db)
            db.commit()

        assert _create_key(owner, {"idp_reauth": proof}).status_code == 403

    def test_a_wrong_second_factor_does_not_spend_the_ticket(self, committed_sessions, sign_in):
        owner, idp_id = self._account(committed_sessions, sign_in)
        with committed_sessions() as db:
            factors = make_mfa(db, owner.user)
            db.commit()
        proof = self._proof(committed_sessions, owner, idp_id, action=_ACTION)

        refused = _create_key(owner, {"idp_reauth": proof, "mfa_code": "000000"})
        accepted = _create_key(owner, {"idp_reauth": proof, "mfa_code": totp_code(factors.secret, steps_ahead=1)})

        assert (refused.status_code, accepted.status_code) == (403, 201)

    def test_an_account_with_a_password_cannot_start_an_identity_provider_step_up(self, committed_sessions, sign_in):
        owner = _local_user(committed_sessions, sign_in)
        with committed_sessions() as db:
            idp_id = make_identity_provider(db, f"idp-{uuid.uuid4().hex[:8]}")
            db.commit()

        response = owner.client.post(
            f"{core_config.ROOT_PATH}/profile/identity-providers/{idp_id}/step-up",
            json={"code_challenge": "c" * 43, "action": _ACTION.value, "redirect": "/settings/security"},
        )

        assert response.status_code == 409


class TestDirectVerification:
    """The check as the services call it, for cases a request cannot reach."""

    def test_a_session_that_is_already_gone_when_its_last_tier_is_spent_ends_nothing(self, db, elapse):
        user = make_user(db)
        store = _store()
        key = f"user:{user.id}:session:{uuid.UUID(int=1)}"
        for _ in range(_LAST_TIER - 1):
            store.record_failed_attempt(key)
            elapse(3 * 3600)

        with pytest.raises(core_exceptions.StepUpFailedError):
            step_up_service.verify_step_up_credentials(user.id, "wrong", None, store, db, session_id=uuid.UUID(int=1))

        assert audit_rows_of(db, account_security_audit_actions.STEP_UP_SESSION_END.id) == []

    def test_a_ticket_cannot_authorise_an_operation_that_names_no_action(self, db):
        with db.begin_nested():
            user = make_user(db, with_password=False)
            idp_id = make_identity_provider(db, f"idp-{uuid.uuid4().hex[:8]}")
            make_identity_link(db, user.id, idp_id, "subject")
        session_id = uuid.uuid4()
        proof = step_up_proof(db, user, session_id, idp_id, action=_ACTION)

        with pytest.raises(core_exceptions.StepUpFailedError):
            step_up_service.verify_step_up_credentials(
                user.id,
                None,
                None,
                _store(),
                db,
                session_id=session_id,
                idp_reauth=auth_schema.IdpReauthProof(ticket=proof["ticket"], code_verifier=proof["code_verifier"]),
                action=None,
            )
