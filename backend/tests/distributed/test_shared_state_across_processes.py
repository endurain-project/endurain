"""State the application keeps in the platform ``StateProvider`` is shared by every API replica.

Two real API processes share only PostgreSQL and Redis. Each test acts on the first replica and observes the effect on
the second, so a counter, claim, ticket or pending login that lived in process memory would show up as a refusal that
never comes (or a replay that is accepted). Everything goes through HTTP; the users are arranged in the deployment's
database.

Not driven here, because they need a third-party identity or provider server: the SSO/OIDC ``state`` and the staged
SSO sign-ins, the identity-provider step-up ticket, the back-channel logout replay guard, and the Strava and Garmin
OAuth, rate-limit and sync state. Their stores are covered by the unit tests of the stores.
"""

import re
from datetime import UTC, datetime, timedelta

import httpx2
import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

import module_registry
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.crud as mfa_crud
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.schema as users_schema
from tests._factories.users import PASSWORD, make_user


@pytest.fixture(autouse=True)
def _user_contributors():
    """Install the hooks that stage the rows every new account starts with, as an API process does."""
    module_registry.configure_user_contributors()
    yield
    users_contributor_registry.clear()


_WEB = {"X-Client-Type": auth_constants.ClientType.WEB.value}


def _start_replicas(cluster, count: int = 2) -> list:
    """Start API replicas one after the other: the first migrates the empty database."""
    return [cluster.start_api(distributed=True) for _ in range(count)]


def _url(api, path: str) -> str:
    return f"http://127.0.0.1:{api.port}/api/v1{path}"


def _make_user(
    cluster, *, totp_secret: str | None = None, password_change_required: bool = False
) -> users_schema.UserRead:
    """Store an active user with a password, and a TOTP factor when a secret is given, in the deployment's database."""
    with Session(cluster.engine) as db:
        user = make_user(db)
        if password_change_required:
            password_hash = credentials_integration.get_password_hasher().hash_password(PASSWORD)
            credentials_integration.set_local_password_hash(user.id, password_hash, db, change_required=True)
        if totp_secret is not None:
            key = cluster.env(distributed=True)["FERNET_KEY"]
            mfa_crud.set_totp_factor(user.id, Fernet(key).encrypt(totp_secret.encode()).decode(), db)
        db.commit()
    return user


def _login(api, username: str, password: str = PASSWORD) -> httpx2.Response:
    return httpx2.post(
        _url(api, "/auth/login"), data={"username": username, "password": password}, headers=_WEB, timeout=30
    )


def _sign_in(api, user: users_schema.UserRead) -> dict[str, str]:
    """Sign in over HTTP and return the headers of an authenticated web client."""
    response = _login(api, user.username)
    assert response.status_code == 200, response.text
    return {**_WEB, "Authorization": f"Bearer {response.json()['access_token']}"}


def _sign_in_with_mfa(api, user: users_schema.UserRead, secret: str) -> dict[str, str]:
    """Sign in an MFA user over HTTP with the code of the next time step, leaving the current step's code unused."""
    challenge = _login(api, user.username).json()["mfa_challenge"]
    code = pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
    response = httpx2.post(
        _url(api, "/auth/mfa/verify"), json={"mfa_challenge": challenge, "mfa_code": code}, headers=_WEB, timeout=30
    )
    assert response.status_code == 200, response.text
    return {**_WEB, "Authorization": f"Bearer {response.json()['access_token']}"}


def _setup_token(log: str) -> str:
    """Read the onboarding setup token a replica logged at startup."""
    for line in log.splitlines():
        match = re.search(r'"setup_token": "([^"]+)"', line)
        if match:
            return match.group(1)
    raise AssertionError(f"no setup token in the log:\n{log[-2000:]}")


class TestLoginLockout:
    def test_failures_counted_on_one_replica_lock_the_sign_in_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        user = _make_user(cluster)

        statuses = [_login(first, user.username, "wrong-password").status_code for _ in range(4)]
        statuses.append(_login(second, user.username, "wrong-password").status_code)
        locked = _login(first, user.username)

        assert statuses == [401] * 5
        assert locked.status_code == 429, locked.text
        assert int(locked.headers["Retry-After"]) > 0
        assert _login(second, user.username).status_code == 429
        assert cluster.error_lines() == []


class TestRateLimit:
    def test_the_bucket_of_a_route_fills_across_replicas(self, cluster):
        first, second = _start_replicas(cluster)

        def validate(api) -> httpx2.Response:
            return httpx2.post(_url(api, "/public/password-reset/validate"), json={"token": "x" * 43}, timeout=30)

        within_limit = [validate(first).status_code for _ in range(5)] + [
            validate(second).status_code for _ in range(5)
        ]
        refused_first, refused_second = validate(first), validate(second)

        assert within_limit == [400] * 10
        assert refused_first.status_code == refused_second.status_code == 429
        assert int(refused_second.headers["Retry-After"]) > 0
        assert refused_second.headers["X-RateLimit-Remaining"] == "0"
        assert cluster.error_lines() == []


class TestMfaSignIn:
    def test_a_pending_login_started_on_one_replica_is_completed_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        secret = pyotp.random_base32()
        user = _make_user(cluster, totp_secret=secret)

        started = _login(first, user.username)
        verified = httpx2.post(
            _url(second, "/auth/mfa/verify"),
            json={"mfa_challenge": started.json()["mfa_challenge"], "mfa_code": pyotp.TOTP(secret).now()},
            headers=_WEB,
            timeout=30,
        )

        assert started.status_code == 200 and started.json()["next_step"] == "mfa"
        assert verified.status_code == 200, verified.text
        assert verified.json()["access_token"]
        assert cluster.error_lines() == []

    def test_a_totp_code_used_on_one_replica_is_refused_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        secret = pyotp.random_base32()
        user = _make_user(cluster, totp_secret=secret)
        totp = pyotp.TOTP(secret)
        code = totp.now()

        def verify(api, code: str) -> httpx2.Response:
            challenge = _login(api, user.username).json()["mfa_challenge"]
            return httpx2.post(
                _url(api, "/auth/mfa/verify"), json={"mfa_challenge": challenge, "mfa_code": code}, headers=_WEB
            )

        accepted = verify(first, code)
        replayed = verify(second, code)
        # The next step's code is inside the accepted drift, so the refusal above was the replay and nothing else.
        next_step = verify(second, totp.at(datetime.now(UTC) + timedelta(seconds=30)))

        assert accepted.status_code == 200, accepted.text
        assert replayed.status_code == 400, replayed.text
        assert next_step.status_code == 200, next_step.text
        assert cluster.error_lines() == []

    def test_wrong_codes_counted_on_both_replicas_end_the_challenge(self, cluster):
        first, second = _start_replicas(cluster)
        secret = pyotp.random_base32()
        user = _make_user(cluster, totp_secret=secret)
        challenge = _login(first, user.username).json()["mfa_challenge"]

        def verify(api, code: str) -> httpx2.Response:
            return httpx2.post(
                _url(api, "/auth/mfa/verify"), json={"mfa_challenge": challenge, "mfa_code": code}, headers=_WEB
            )

        wrong = [verify(first, "000000").status_code, verify(first, "000001").status_code]
        ended = verify(second, "000002").status_code
        after = verify(first, pyotp.TOTP(secret).now())

        assert wrong == [400, 400]
        assert ended == 401
        assert after.status_code == 401, after.text
        assert cluster.error_lines() == []


class TestStepUp:
    def test_an_mfa_secret_set_up_on_one_replica_is_enabled_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        user = _make_user(cluster)
        headers = _sign_in(first, user)

        setup = httpx2.post(_url(first, "/profile/mfa/setup"), headers=headers, timeout=30)
        enabled = httpx2.post(
            _url(second, "/profile/mfa/enable"),
            json={"step_up": {"current_password": PASSWORD}, "totp_code": pyotp.TOTP(setup.json()["secret"]).now()},
            headers=headers,
            timeout=30,
        )

        assert setup.status_code == 201, setup.text
        assert enabled.status_code == 200, enabled.text
        assert cluster.scalar("SELECT count(*) FROM mfa_factors WHERE user_id = :id", id=user.id) == 1
        assert cluster.error_lines() == []

    def test_failed_step_ups_counted_on_both_replicas_lock_the_session(self, cluster):
        first, second = _start_replicas(cluster)
        secret = pyotp.random_base32()
        user = _make_user(cluster, totp_secret=secret)
        headers = _sign_in_with_mfa(first, user, secret)

        def regenerate(api, password: str) -> httpx2.Response:
            body = {
                "step_up": {"current_password": password, "mfa_code": "000000"},
                "revoke_other_sessions": False,
            }
            return httpx2.post(_url(api, "/profile/mfa/backup-codes"), json=body, headers=headers, timeout=30)

        statuses = [regenerate(first, "wrong-password").status_code for _ in range(4)]
        statuses.append(regenerate(second, "wrong-password").status_code)
        locked = regenerate(first, PASSWORD)

        assert statuses == [403] * 5, statuses
        assert locked.status_code == 429, locked.text
        assert cluster.error_lines() == []

    def test_a_totp_code_used_for_step_up_on_one_replica_is_refused_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        secret = pyotp.random_base32()
        user = _make_user(cluster, totp_secret=secret)
        headers = _sign_in_with_mfa(first, user, secret)
        code = pyotp.TOTP(secret).now()

        def regenerate(api, mfa_code: str) -> httpx2.Response:
            body = {"step_up": {"current_password": PASSWORD, "mfa_code": mfa_code}, "revoke_other_sessions": False}
            return httpx2.post(_url(api, "/profile/mfa/backup-codes"), json=body, headers=headers, timeout=30)

        accepted = regenerate(first, code)
        replayed = regenerate(second, code)

        assert accepted.status_code == 201, accepted.text
        assert replayed.status_code == 403, replayed.text
        assert cluster.error_lines() == []


class TestPendingPasswordChange:
    def test_a_password_change_started_on_one_replica_is_finished_once_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        user = _make_user(cluster, password_change_required=True)

        started = _login(first, user.username)
        challenge = started.json()["password_change_challenge"]

        def change(api) -> httpx2.Response:
            return httpx2.post(
                _url(api, "/auth/password-change"),
                json={"password_change_challenge": challenge, "password": "Replacement-Password-5678!"},
                headers=_WEB,
                timeout=60,
            )

        finished = change(second)
        replayed = change(first)

        assert started.json()["next_step"] == "password_change"
        assert finished.status_code == 200, finished.text
        assert replayed.status_code == 401, replayed.text
        assert cluster.error_lines() == []


class TestWebSocketTickets:
    def test_a_ticket_issued_on_one_replica_is_accepted_once_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        user = _make_user(cluster)
        headers = _sign_in(first, user)
        ticket = httpx2.post(_url(first, "/ws/ticket"), headers=headers, timeout=30).json()["ticket"]

        with connect(f"ws://127.0.0.1:{second.port}/api/v1/ws?ticket={ticket}", open_timeout=15):
            pass
        with pytest.raises(InvalidStatus) as replay:
            connect(f"ws://127.0.0.1:{first.port}/api/v1/ws?ticket={ticket}", open_timeout=15)

        assert replay.value.response.status_code == 403
        assert cluster.error_lines() == []


class TestOnboardingToken:
    def test_a_setup_token_minted_by_one_replica_creates_the_first_administrator_on_the_other(self, cluster):
        first, second = _start_replicas(cluster)
        token = _setup_token(cluster.log(first))
        admin = {"name": "Owner", "username": "owner", "email": "owner@example.com", "password": "Owner-Password-1234!"}

        unknown = httpx2.post(_url(second, "/public/onboarding"), json={**admin, "token": "x" * 43}, timeout=60)
        created = httpx2.post(_url(second, "/public/onboarding"), json={**admin, "token": token}, timeout=60)
        again = httpx2.post(_url(first, "/public/onboarding"), json={**admin, "token": token}, timeout=60)

        assert unknown.status_code == 400, unknown.text
        assert created.status_code == 201, created.text
        assert again.status_code == 409, again.text
        assert cluster.scalar("SELECT count(*) FROM users") == 1
        assert cluster.error_lines() == []
