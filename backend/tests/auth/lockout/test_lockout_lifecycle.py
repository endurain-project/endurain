"""Five failed password sign-ins lock the username on that client network; the lock lifts when its time passes."""

import jasil.runtime
import jasil.testing as jasil_testing
from fastapi.testclient import TestClient

import core.config as core_config
import modules.auth.lockout.audit_actions as lockout_audit_actions
import modules.auth.login_audit.audit_actions as login_audit_actions
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_user

_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_WRONG_PASSWORD = "Wrong-Password-0000!"
_FIRST_TIER_FAILURES = 5
_FIRST_LOCK_SECONDS = 300


def _sign_in(client: TestClient, username: str, password: str):
    return client.post(_LOGIN, data={"username": username, "password": password}, headers={"X-Client-Type": "web"})


def _fail(client: TestClient, username: str, times: int) -> list[int]:
    return [_sign_in(client, username, _WRONG_PASSWORD).status_code for _ in range(times)]


def _user(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return user


def _login_outcomes(committed_sessions) -> list[tuple[str, str | None]]:
    rows = audit_rows(committed_sessions, login_audit_actions.LOGIN)
    return [(row.outcome, row.details["reason"]) for row in rows]


def _let_the_lock_pass() -> None:
    """Advance the platform clock past the five minutes of the first lock tier."""
    clock = jasil.runtime.get_active_platform().clock
    assert isinstance(clock, jasil_testing.FixedClock)
    clock.advance(_FIRST_LOCK_SECONDS + 1)


class TestPasswordSignInLockout:
    def test_five_failures_lock_the_username_and_a_correct_password_is_then_refused(self, client, committed_sessions):
        user = _user(committed_sessions)

        statuses = _fail(client, user.username, _FIRST_TIER_FAILURES)
        locked = _sign_in(client, user.username, PASSWORD)

        assert statuses == [401] * _FIRST_TIER_FAILURES
        assert locked.status_code == 429
        assert locked.json()["type"] == "urn:endurain:error:too-many-requests"
        assert int(locked.headers["Retry-After"]) in range(1, 301)
        assert _login_outcomes(committed_sessions) == [("failure", "invalid_credentials")] * _FIRST_TIER_FAILURES + [
            ("denied", "locked_out")
        ]
        applied = audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY)
        assert [(row.outcome, row.details) for row in applied] == [
            ("success", {"counter": "login", "failed_attempts": _FIRST_TIER_FAILURES})
        ]

    def test_four_failures_do_not_lock(self, client, committed_sessions):
        user = _user(committed_sessions)

        _fail(client, user.username, _FIRST_TIER_FAILURES - 1)

        assert _sign_in(client, user.username, PASSWORD).status_code == 200
        assert audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY) == []

    def test_the_lock_lifts_when_its_time_passes_and_the_password_signs_in(self, client, committed_sessions):
        user = _user(committed_sessions)
        _fail(client, user.username, _FIRST_TIER_FAILURES)
        assert _sign_in(client, user.username, PASSWORD).status_code == 429

        _let_the_lock_pass()

        assert _sign_in(client, user.username, PASSWORD).status_code == 200

    def test_a_successful_sign_in_clears_the_failure_count(self, client, committed_sessions):
        user = _user(committed_sessions)
        _fail(client, user.username, _FIRST_TIER_FAILURES - 1)
        assert _sign_in(client, user.username, PASSWORD).status_code == 200

        statuses = _fail(client, user.username, _FIRST_TIER_FAILURES - 1)

        assert statuses == [401] * (_FIRST_TIER_FAILURES - 1)
        assert audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY) == []

    def test_the_lock_holds_the_client_network_that_failed_and_no_other(self, app, committed_sessions):
        user = _user(committed_sessions)
        failing = TestClient(app, client=("203.0.113.7", 50000))
        elsewhere = TestClient(app, client=("198.51.100.9", 50000))
        _fail(failing, user.username, _FIRST_TIER_FAILURES)

        assert _sign_in(failing, user.username, PASSWORD).status_code == 429
        assert _sign_in(elsewhere, user.username, PASSWORD).status_code == 200

    def test_a_username_that_names_no_account_locks_the_same_way(self, client, committed_sessions):
        statuses = _fail(client, "nobody-here", _FIRST_TIER_FAILURES)
        locked = _sign_in(client, "nobody-here", PASSWORD)

        assert statuses == [401] * _FIRST_TIER_FAILURES
        assert locked.status_code == 429
        applied = audit_rows(committed_sessions, lockout_audit_actions.LOCKOUT_APPLY)
        assert [row.details["counter"] for row in applied] == ["login"]

    def test_the_lock_is_keyed_by_the_username_in_any_case(self, client, committed_sessions):
        user = _user(committed_sessions)
        _fail(client, user.username.upper(), _FIRST_TIER_FAILURES)

        assert _sign_in(client, user.username, PASSWORD).status_code == 429
