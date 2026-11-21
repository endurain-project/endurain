"""First-run onboarding: the setup token creates the first administrator once, on the real application."""

import gzip
import threading
import time
from pathlib import Path

import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from jasil.providers import StateBackendUnavailableError

import core.config as core_config
import modules.auth.credentials.service as credentials_service
import modules.auth.onboarding.audit_actions as onboarding_audit_actions
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
from tests._factories.breach import fake_range_api
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user

_ONBOARDING = f"{core_config.ROOT_PATH}/public/onboarding"
_LOGIN = f"{core_config.ROOT_PATH}/auth/login"
_PASSWORD = "A long first administrator passphrase 1!"


def _blocklist_entry() -> str:
    data = Path(credentials_service.__file__).parent / "data" / "password_blocklist.txt.gz"
    with gzip.open(data, "rt", encoding="utf-8") as handle:
        return handle.readline().rstrip("\n")


def _setup_token() -> str:
    return onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).issue()


def _body(token: str, **fields: str) -> dict[str, str]:
    return {
        "token": token,
        "name": "Owner",
        "username": "owner",
        "email": "owner@example.com",
        "password": _PASSWORD,
    } | fields


def _users(committed_sessions) -> list[users_models.Users]:
    with committed_sessions() as db:
        return list(db.scalars(sa.select(users_models.Users)))


def _wait_for_advisory_lock_waiter(committed_sessions) -> None:
    """Poll until a request waits on an advisory lock; each poll ends its transaction so the read is fresh."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with committed_sessions() as db:
            waiting = db.scalar(sa.text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"))
            db.rollback()
        if waiting:
            return
    raise AssertionError("no request waited for the first-administrator lock")


def _reasons(committed_sessions) -> list[str]:
    rows = audit_rows(committed_sessions, onboarding_audit_actions.ONBOARDING_REFUSE)
    assert {row.outcome for row in rows} <= {"denied"}
    return [row.details["reason"] for row in rows]


class TestStatus:
    def test_onboarding_is_required_exactly_while_no_account_exists(self, client, committed_sessions):
        assert client.get(_ONBOARDING).json() == {"onboarding_required": True}

        with committed_sessions() as db:
            make_user(db)
            db.commit()

        assert client.get(_ONBOARDING).json() == {"onboarding_required": False}


class TestCreatingTheFirstAdministrator:
    def test_a_valid_token_creates_an_active_verified_administrator_who_signs_in(self, client, committed_sessions):
        response = client.post(_ONBOARDING, json=_body(_setup_token()))

        assert response.status_code == 201
        assert response.headers["ETag"] == '"1"'
        assert response.json()["access_type"] == "admin"
        (row,) = _users(committed_sessions)
        assert (row.username, row.access_type, row.active, row.email_verified) == ("owner", "admin", True, True)
        login = client.post(_LOGIN, data={"username": "owner", "password": _PASSWORD}, headers={"X-Client-Type": "web"})
        assert login.status_code == 200
        assert _reasons(committed_sessions) == []

    def test_the_token_works_once(self, client, committed_sessions):
        token = _setup_token()

        first = client.post(_ONBOARDING, json=_body(token))
        second = client.post(_ONBOARDING, json=_body(token, username="intruder", email="intruder@example.com"))

        assert (first.status_code, second.status_code) == (201, 409)
        assert [row.username for row in _users(committed_sessions)] == ["owner"]
        assert _reasons(committed_sessions) == ["account_exists"]

    def test_an_unknown_token_is_refused_and_audited_without_the_token(self, client, committed_sessions):
        response = client.post(_ONBOARDING, json=_body("not-a-setup-token"))

        assert response.status_code == 400
        assert _users(committed_sessions) == []
        assert _reasons(committed_sessions) == ["invalid_token"]
        rows = audit_rows(committed_sessions, onboarding_audit_actions.ONBOARDING_REFUSE)
        assert "not-a-setup-token" not in repr(rows[0].details)

    def test_an_existing_account_is_a_conflict_that_leaves_the_token_valid(self, client, committed_sessions):
        token = _setup_token()
        with committed_sessions() as db:
            make_user(db)
            db.commit()

        response = client.post(_ONBOARDING, json=_body(token))

        assert response.status_code == 409
        assert _reasons(committed_sessions) == ["account_exists"]
        assert onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).exists(token)

    @pytest.mark.parametrize(
        ("password", "problem"),
        [("short", "password-too-short"), ("owner@example.com", "password-matches-account")],
    )
    def test_a_password_the_policy_refuses_is_422_and_does_not_burn_the_token(
        self, client, committed_sessions, password, problem
    ):
        token = _setup_token()

        refused = client.post(_ONBOARDING, json=_body(token, password=password))

        assert refused.status_code == 422
        assert refused.json()["type"] == f"urn:endurain:error:{problem}"
        assert _users(committed_sessions) == []
        assert _reasons(committed_sessions) == ["password_policy"]
        assert client.post(_ONBOARDING, json=_body(token)).status_code == 201

    def test_a_common_password_is_refused_under_the_administrator_minimum(self, client, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, password_length_admin_users=8)
            db.commit()

        refused = client.post(_ONBOARDING, json=_body(_setup_token(), password=_blocklist_entry()))

        assert refused.status_code == 422
        assert refused.json()["type"] == "urn:endurain:error:password-too-common"
        assert _users(committed_sessions) == []

    def test_a_breached_password_is_refused_and_audited_as_a_policy_refusal(
        self, client, committed_sessions, monkeypatch
    ):
        range_api = fake_range_api(monkeypatch)
        range_api.breach(_PASSWORD)
        with committed_sessions() as db:
            edit_server_settings(db, password_breach_check_enabled=True)
            db.commit()
        token = _setup_token()

        refused = client.post(_ONBOARDING, json=_body(token))

        assert refused.status_code == 422
        assert refused.json()["type"] == "urn:endurain:error:password-breached"
        assert _users(committed_sessions) == []
        assert _reasons(committed_sessions) == ["password_policy"]
        assert onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).exists(token)

    def test_concurrent_requests_with_one_token_create_exactly_one_administrator(self, app, committed_sessions):
        token = _setup_token()
        barrier = threading.Barrier(4)
        statuses: list[int] = []

        def attempt(n: int) -> None:
            client = TestClient(app)
            barrier.wait()
            body = _body(token, username=f"owner{n}", email=f"owner{n}@example.com")
            statuses.append(client.post(_ONBOARDING, json=body).status_code)

        threads = [threading.Thread(target=attempt, args=(n,)) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert statuses.count(201) == 1
        assert len(statuses) == 4 and set(statuses) <= {201, 400, 409}
        assert len(_users(committed_sessions)) == 1
        assert len(_reasons(committed_sessions)) == 3

    def test_an_account_created_while_the_request_waits_for_the_lock_is_a_conflict(self, app, committed_sessions):
        token = _setup_token()
        statuses: list[int] = []
        with committed_sessions() as holder:
            users_crud.lock_first_admin_creation(holder)
            request = threading.Thread(
                target=lambda: statuses.append(TestClient(app).post(_ONBOARDING, json=_body(token)).status_code)
            )
            request.start()
            _wait_for_advisory_lock_waiter(committed_sessions)
            make_user(holder)
            holder.commit()
            request.join(timeout=60)

        assert statuses == [409]
        assert len(_users(committed_sessions)) == 1
        assert _reasons(committed_sessions) == ["account_exists"]

    def test_a_token_used_by_another_request_while_this_one_waits_creates_nothing(self, app, committed_sessions):
        token = _setup_token()
        statuses: list[int] = []
        with committed_sessions() as holder:
            users_crud.lock_first_admin_creation(holder)
            request = threading.Thread(
                target=lambda: statuses.append(TestClient(app).post(_ONBOARDING, json=_body(token)).status_code)
            )
            request.start()
            _wait_for_advisory_lock_waiter(committed_sessions)
            assert onboarding_token_store.OnboardingTokenStore(platform_runtime.get_state()).claim(token) is True
            holder.rollback()
            request.join(timeout=60)

        assert statuses == [400]
        assert _users(committed_sessions) == []
        assert _reasons(committed_sessions) == ["invalid_token"]

    @pytest.mark.parametrize("field", ["access_type", "active", "email_verified", "pending_admin_approval"])
    def test_a_field_that_would_choose_the_role_or_state_is_rejected(self, client, committed_sessions, field):
        response = client.post(_ONBOARDING, json=_body(_setup_token()) | {field: "admin"})

        assert response.status_code == 422
        assert _users(committed_sessions) == []

    @pytest.mark.parametrize("missing", ["token", "name", "username", "email", "password"])
    def test_every_field_is_required(self, client, missing):
        body = {key: value for key, value in _body(_setup_token()).items() if key != missing}

        assert client.post(_ONBOARDING, json=body).status_code == 422

    def test_an_unavailable_state_backend_answers_503_and_creates_nothing(
        self, client, committed_sessions, monkeypatch
    ):
        token = _setup_token()

        def down(*_args, **_kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(platform_runtime.get_state(), "get", down)

        response = client.post(_ONBOARDING, json=_body(token))

        assert response.status_code == 503
        assert _users(committed_sessions) == []
