"""The Garmin Connect routes, through the production application: real sign-in, step-up, stores and database."""

import threading
import time
from datetime import timedelta

import garminconnect
import pytest
from sqlalchemy import select

import core.config as core_config
import core.timezone as core_timezone
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.constants as garmin_constants
import modules.garmin.sync_service as garmin_sync_service
import modules.users.users_integrations.models as user_integrations_models
from tests._factories import garmin as garmin_factories
from tests._factories.auth import SignedIn
from tests._factories.tokens import audit_rows
from tests._factories.users import PASSWORD, make_user
from tests.garmin.conftest import stored_access_token, stored_token

_URL = f"{core_config.ROOT_PATH}/garmin"
_BODY = {"username": "me@example.com", "password": "pw", "is_cn": False}
_STEP_UP = {"step_up": {"current_password": PASSWORD}}


def _today():
    """The user's today: the tests' users have a UTC timezone, and the code reads the day from the platform clock."""
    return core_timezone.today_in(core_timezone.or_default("UTC"))


@pytest.fixture
def me(sign_in, committed_sessions) -> SignedIn:
    """A signed-in user who has not linked Garmin Connect."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        db.commit()
    return sign_in(user)


@pytest.fixture
def linked_me(sign_in, linked) -> SignedIn:
    """A signed-in user with Garmin Connect linked."""
    return sign_in(linked)


class TestLink:
    def test_a_link_answers_running_at_once_and_the_poll_reports_the_outcome(
        self, committed_sessions, account, me, link_pool
    ):
        response = me.client.post(f"{_URL}/link", json=_BODY)

        body = response.json()
        assert response.status_code == 202
        assert body["kind"] == "garmin_link"
        assert (body["status"], body["error_code"], body["finished_at"], body["mfa_required"]) == (
            "running",
            None,
            None,
            False,
        )
        assert response.headers["Content-Location"] == f"{core_config.ROOT_PATH}/jobs/{body['id']}"
        link_pool.shutdown(wait=True)
        polled = me.client.get(response.headers["Content-Location"]).json()
        assert (polled["id"], polled["status"]) == (body["id"], "succeeded")
        assert stored_access_token(committed_sessions, me.user.id) == "login-access"

    def test_a_second_link_while_one_runs_is_a_conflict_naming_the_running_job(
        self, account, me, link_pool, blocked_pool
    ):
        account.login_script = lambda garmin: blocked_pool.release.wait(10)
        first = me.client.post(f"{_URL}/link", json=_BODY)

        second = me.client.post(f"{_URL}/link", json=_BODY)

        assert (first.status_code, second.status_code) == (202, 409)
        assert second.headers["Content-Location"] == f"{core_config.ROOT_PATH}/jobs/{first.json()['id']}"
        assert len(account.clients) <= 1

    def test_a_failed_link_reports_its_reason_and_can_be_retried(self, account, me, link_pool):
        def refuse(_garmin):
            raise garminconnect.GarminConnectAuthenticationError("bad password")

        account.login_script = refuse
        first = me.client.post(f"{_URL}/link", json=_BODY)
        link_pool.shutdown(wait=True)

        polled = me.client.get(first.headers["Content-Location"]).json()
        assert (polled["status"], polled["error_code"]) == ("failed", "invalid_credentials")
        assert me.client.post(f"{_URL}/link", json=_BODY).status_code == 202

    def test_oversized_credentials_are_a_validation_error(self, me):
        assert me.client.post(f"{_URL}/link", json={**_BODY, "password": "x" * 1000}).status_code == 422


class TestMfa:
    def test_a_code_with_no_login_waiting_is_a_conflict(self, me, link_states):
        link_states.begin(me.user.id, conflict="busy")

        assert me.client.post(f"{_URL}/mfa", json={"mfa_code": "123456"}).status_code == 409

    def test_a_code_is_accepted_while_the_login_waits_and_reaches_the_login(
        self, account, me, link_pool, link_states, mfa_codes, monkeypatch
    ):
        received: list[str] = []
        waiting = threading.Event()

        def login(garmin):
            received.append(garmin.prompt_mfa())

        def poll_for_the_code(_seconds):
            waiting.set()
            deadline = time.monotonic() + 10
            while mfa_codes.get_code(me.user.id) is None and time.monotonic() < deadline:
                threading.Event().wait(0.01)

        account.login_script = login
        monkeypatch.setattr(time, "sleep", poll_for_the_code)
        me.client.post(f"{_URL}/link", json=_BODY)
        assert waiting.wait(10)

        response = me.client.post(f"{_URL}/mfa", json={"mfa_code": "123 456"})
        link_pool.shutdown(wait=True)

        assert response.status_code == 204
        assert received == ["123456"]

    @pytest.mark.parametrize("code", ["1" * 100, "12 34!"])
    def test_an_oversized_or_non_alphanumeric_code_is_a_validation_error(self, me, code):
        assert me.client.post(f"{_URL}/mfa", json={"mfa_code": code}).status_code == 422


class TestSyncRoutes:
    def test_a_gear_sync_is_queued_and_polls_to_its_outcome(self, committed_sessions, account, linked_me, sync_pool):
        account.gear = [garmin_factories.gear_payload("g-1")]

        response = linked_me.client.post(f"{_URL}/gear")
        body = response.json()
        sync_pool.shutdown(wait=True)

        assert response.status_code == 202
        assert (body["kind"], body["status"]) == ("garmin_sync_gear", "queued")
        assert response.headers["Content-Location"] == f"{core_config.ROOT_PATH}/jobs/{body['id']}"
        assert linked_me.client.get(response.headers["Content-Location"]).json()["status"] == "succeeded"

    def test_a_second_gear_sync_while_one_is_pending_is_a_conflict(self, linked_me, blocked_pool, monkeypatch):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(3))

        first = linked_me.client.post(f"{_URL}/gear")
        second = linked_me.client.post(f"{_URL}/gear")

        assert (first.status_code, second.status_code) == (202, 409)

    def test_a_health_sync_is_queued_and_names_its_job(self, linked_me, sync_pool, account):
        day = _today().isoformat()

        response = linked_me.client.post(f"{_URL}/health", params={"start_date": day, "end_date": day})
        sync_pool.shutdown(wait=True)

        body = response.json()
        assert response.status_code == 202
        assert (body["kind"], body["status"]) == ("garmin_sync_health", "queued")
        assert response.headers["Content-Location"] == f"{core_config.ROOT_PATH}/jobs/{body['id']}"

    def test_a_reversed_health_range_is_a_validation_error(self, linked_me):
        today = _today()

        response = linked_me.client.post(
            f"{_URL}/health",
            params={"start_date": today.isoformat(), "end_date": (today - timedelta(days=1)).isoformat()},
        )

        assert response.status_code == 422

    def test_a_health_range_beyond_the_cap_is_refused_and_nothing_is_queued(self, linked_me, sync_states):
        today = _today()
        too_long = today - timedelta(days=garmin_constants.MAX_HEALTH_RANGE_DAYS)

        response = linked_me.client.post(
            f"{_URL}/health", params={"start_date": too_long.isoformat(), "end_date": today.isoformat()}
        )

        assert response.status_code == 400
        assert sync_states.get(linked_me.user.id, garmin_constants.SyncKind.HEALTH) is None

    def test_an_activities_range_ending_in_the_future_is_refused(self, linked_me):
        tomorrow = (_today() + timedelta(days=1)).isoformat()

        response = linked_me.client.post(f"{_URL}/activities", params={"start_date": tomorrow, "end_date": tomorrow})

        assert response.status_code == 400

    def test_the_status_routes_are_gone(self, linked_me):
        assert linked_me.client.get(f"{_URL}/link/status").status_code in (404, 405)
        assert linked_me.client.get(f"{_URL}/sync/gear").status_code in (404, 405)


class TestUnlink:
    def test_unlinking_clears_the_token_and_gear_sync_and_is_audited(self, committed_sessions, make_linked, sign_in):
        user = make_linked(sync_gear=True)
        me = sign_in(user)

        response = me.client.post(f"{_URL}/unlink", json=_STEP_UP)

        assert response.status_code == 204
        assert response.content == b""
        assert stored_token(committed_sessions, user.id) is None
        with committed_sessions() as db:
            row = db.scalars(select(user_integrations_models.UsersIntegrations).filter_by(user_id=user.id)).one()
            assert row.garminconnect_sync_gear is False
        [audited] = audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_UNLINK)
        assert (audited.target_id, audited.target_owner_id) == (str(user.id), str(user.id))

    def test_a_wrong_password_unlinks_nothing(self, committed_sessions, linked, sign_in):
        me = sign_in(linked)

        response = me.client.post(f"{_URL}/unlink", json={"step_up": {"current_password": "not-the-password"}})

        assert response.status_code in (401, 403)
        assert stored_token(committed_sessions, linked.id) is not None
        assert audit_rows(committed_sessions, garmin_audit_actions.ACCOUNT_UNLINK) == []

    def test_unlinking_needs_a_step_up_body_and_the_delete_route_is_gone(self, committed_sessions, linked, sign_in):
        me = sign_in(linked)

        assert me.client.post(f"{_URL}/unlink", json={}).status_code == 422
        assert me.client.delete(f"{_URL}/link").status_code == 405
        assert stored_token(committed_sessions, linked.id) is not None
