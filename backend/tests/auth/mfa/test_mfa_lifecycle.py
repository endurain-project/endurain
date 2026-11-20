"""A TOTP or backup code works once, a backup code is consumed exactly once, and wrong codes lock the account."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import jasil.runtime
import sqlalchemy as sa
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.lockout.audit_actions as lockout_audit_actions
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa_backup_codes.audit_actions as backup_codes_audit_actions
import modules.auth.mfa_backup_codes.models as backup_codes_models
import modules.auth.sessions.models as sessions_models
import modules.users.users.schema as users_schema
from tests._factories.tokens import MfaFactors, audit_rows, make_mfa, totp_code
from tests._factories.users import PASSWORD, make_user

_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_VERIFY = f"{core_config.ROOT_PATH}/auth/mfa/verify"
_PROFILE = f"{core_config.ROOT_PATH}/profile"
_WEB = {"X-Client-Type": "web"}
_CLIENT_ADDRESS = "testclient"


def _enrolled_user(committed_sessions) -> tuple[users_schema.UserRead, MfaFactors]:
    with committed_sessions() as db:
        user = make_user(db)
        factors = make_mfa(db, user)
        db.commit()
    return user, factors


def _challenge(client: TestClient, user: users_schema.UserRead) -> str:
    response = client.post(_LOGIN, data={"username": user.username, "password": PASSWORD}, headers=_WEB)
    assert response.status_code == 200
    assert response.json()["next_step"] == "mfa"
    return response.json()["mfa_challenge"]


def _verify(client: TestClient, challenge: str, code: str):
    return client.post(_VERIFY, json={"mfa_challenge": challenge, "mfa_code": code}, headers=_WEB)


def _wrong_code(secret: str) -> str:
    """A six-digit code the secret accepts at none of the current and neighbouring steps."""
    accepted = {totp_code(secret, steps_ahead=offset) for offset in (-1, 0, 1)}
    return next(code for code in (f"{n:06d}" for n in range(1_000_000)) if code not in accepted)


def _sessions_of(committed_sessions, user_id: uuid.UUID) -> int:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(sa.func.count())
            .select_from(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.user_id == user_id)
        )


def _login_rows(committed_sessions):
    return audit_rows(committed_sessions, login_audit_actions.LOGIN)


def _expire_mfa_lock(username: str) -> None:
    """Move the end of the account's MFA lock into the past, as if its five minutes had passed."""
    state = jasil.runtime.get_active_platform().state
    store = pending_login_store.PendingMFALogin(state)
    key = store._client_key(username, _CLIENT_ADDRESS)
    gate = store._lockout._gate_key(key)
    assert state.get(gate) is not None
    state.set(gate, b"1")


class TestTotpCode:
    def test_a_code_completes_the_sign_in_once_and_its_replay_is_refused(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        code = totp_code(factors.secret, steps_ahead=1)

        first = _verify(TestClient(app), _challenge(TestClient(app), user), code)
        replay = _verify(TestClient(app), _challenge(TestClient(app), user), code)

        assert first.status_code == 200
        authorised = TestClient(
            app, headers={"Authorization": f"Bearer {first.json()['access_token']}", "X-Client-Type": "web"}
        )
        assert authorised.get(_PROFILE).status_code == 200
        assert replay.status_code == 400
        assert replay.json()["type"] == "urn:endurain:error:invalid-mfa-code"
        assert _sessions_of(committed_sessions, user.id) == 1
        failures = [row for row in _login_rows(committed_sessions) if row.outcome == "failure"]
        assert [(row.target_id, row.details["reason"], row.details["mfa"]) for row in failures] == [
            (str(user.id), "invalid_mfa_code", True)
        ]

    def test_a_wrong_code_is_refused_audited_and_creates_no_session(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)

        response = _verify(TestClient(app), _challenge(TestClient(app), user), _wrong_code(factors.secret))

        assert response.status_code == 400
        assert _sessions_of(committed_sessions, user.id) == 0
        rows = _login_rows(committed_sessions)
        assert [(row.outcome, row.target_id, row.details["reason"]) for row in rows] == [
            ("failure", str(user.id), "invalid_mfa_code")
        ]


class TestBackupCode:
    def test_a_backup_code_works_once_and_is_audited_with_the_codes_left(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        code = factors.backup_codes[0]

        first = _verify(TestClient(app), _challenge(TestClient(app), user), code)
        second = _verify(TestClient(app), _challenge(TestClient(app), user), code)

        assert first.status_code == 200
        assert second.status_code == 400
        with committed_sessions() as db:
            used = db.scalars(
                sa.select(backup_codes_models.MFABackupCode.used).where(
                    backup_codes_models.MFABackupCode.user_id == user.id
                )
            ).all()
        assert sorted(used) == [False] * 9 + [True]
        rows = audit_rows(committed_sessions, backup_codes_audit_actions.BACKUP_CODE_USE)
        assert [(row.outcome, row.target_id, row.details) for row in rows] == [
            ("success", str(user.id), {"remaining_codes": 9})
        ]

    def test_another_unused_code_still_works(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        _verify(TestClient(app), _challenge(TestClient(app), user), factors.backup_codes[0])

        response = _verify(TestClient(app), _challenge(TestClient(app), user), factors.backup_codes[1])

        assert response.status_code == 200

    def test_two_simultaneous_uses_of_one_backup_code_succeed_once(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        code = factors.backup_codes[0]
        challenges = [_challenge(TestClient(app), user) for _ in range(2)]
        barrier = threading.Barrier(2)

        def use(challenge: str):
            client = TestClient(app)
            barrier.wait(timeout=10)
            return _verify(client, challenge, code)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [future.result(timeout=60) for future in [pool.submit(use, c) for c in challenges]]

        assert sorted(response.status_code for response in responses) == [200, 400]
        assert _sessions_of(committed_sessions, user.id) == 1
        with committed_sessions() as db:
            used = db.scalars(
                sa.select(sa.func.count())
                .select_from(backup_codes_models.MFABackupCode)
                .where(
                    backup_codes_models.MFABackupCode.user_id == user.id,
                    backup_codes_models.MFABackupCode.used.is_(True),
                )
            ).one()
        assert used == 1
        assert len(audit_rows(committed_sessions, backup_codes_audit_actions.BACKUP_CODE_USE)) == 1


class TestWrongCodesAndLockout:
    def test_the_third_wrong_code_ends_the_challenge_and_a_right_code_cannot_revive_it(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        client = TestClient(app)
        challenge = _challenge(client, user)
        wrong = _wrong_code(factors.secret)

        statuses = [_verify(client, challenge, wrong).status_code for _ in range(3)]
        revived = _verify(client, challenge, totp_code(factors.secret, steps_ahead=1))

        assert statuses == [400, 400, 401]
        assert revived.status_code == 401
        assert revived.json()["type"] == "urn:endurain:error:session-ended"
        assert _sessions_of(committed_sessions, user.id) == 0
        failures = [(row.outcome, row.details["reason"]) for row in _login_rows(committed_sessions)]
        assert failures == [("failure", "invalid_mfa_code")] * 3 + [("failure", "mfa_challenge_expired")]

    def test_five_wrong_codes_lock_the_account_and_the_lock_is_audited(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        client = TestClient(app)
        wrong = _wrong_code(factors.secret)
        first = _challenge(client, user)
        second = _challenge(client, user)
        for challenge, count in ((first, 3), (second, 2)):
            for _ in range(count):
                _verify(client, challenge, wrong)

        locked = _verify(client, second, totp_code(factors.secret, steps_ahead=1))

        assert locked.status_code == 429
        assert _sessions_of(committed_sessions, user.id) == 0
        applied = audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY)
        assert [(row.outcome, row.target_id, row.details) for row in applied] == [
            ("success", str(user.id), {"counter": "mfa", "failed_attempts": 5})
        ]
        last = _login_rows(committed_sessions)[-1]
        assert (last.outcome, last.target_id, last.details["reason"]) == ("denied", str(user.id), "locked_out")

    def test_the_lock_lifts_when_its_time_passes(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        client = TestClient(app)
        wrong = _wrong_code(factors.secret)
        first = _challenge(client, user)
        second = _challenge(client, user)
        for challenge, count in ((first, 3), (second, 2)):
            for _ in range(count):
                _verify(client, challenge, wrong)
        code = totp_code(factors.secret, steps_ahead=1)
        assert _verify(client, second, code).status_code == 429

        _expire_mfa_lock(user.username)

        response = _verify(client, second, code)
        assert response.status_code == 200
        assert _sessions_of(committed_sessions, user.id) == 1

    def test_a_successful_sign_in_clears_the_count_of_wrong_codes(self, app, committed_sessions):
        user, factors = _enrolled_user(committed_sessions)
        client = TestClient(app)
        wrong = _wrong_code(factors.secret)
        for _ in range(4):
            _verify(client, _challenge(client, user), wrong)
        assert _verify(client, _challenge(client, user), totp_code(factors.secret, steps_ahead=1)).status_code == 200

        for _ in range(4):
            _verify(client, _challenge(client, user), wrong)

        assert audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY) == []
