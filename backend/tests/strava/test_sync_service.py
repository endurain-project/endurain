"""Queued Strava gear syncs and unlinks run off the request, once per user, and record their outcome."""

import threading
import uuid
from datetime import timedelta

import jasil.audit.models as audit_models
import jasil.jobs.models as jobs_models
import jasil.jobs.registry as jobs_registry
import jasil.runtime as platform_runtime
import pytest
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from sqlalchemy import select

import core.attempt_state as core_attempt_state
import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.gears.gear.integration_service as gears_integration
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.constants as strava_constants
import modules.strava.events as strava_events
import modules.strava.integration_service as strava_integration
import modules.strava.subscriber_registry as strava_subscriber_registry
import modules.strava.subscribers as strava_subscribers
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store
import modules.users.users_integrations.integration_service as user_integrations_integration
from tests._factories import strava as strava_factories
from tests._factories.users import PASSWORD, make_user

_API = core_config.ROOT_PATH
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_UNLINK_AUDIT = strava_audit_actions.ACCOUNT_UNLINK.id
GEAR = strava_constants.SyncKind.GEAR
UNLINK = strava_constants.SyncKind.UNLINK
Status = strava_constants.SyncStatus


@pytest.fixture
def states():
    return strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        strava_factories.link_strava(db, created.id)
        db.commit()
    return created


def _payload(user, job_id, kind=GEAR):
    return strava_events.SyncRequestedPayload(user_id=user.id, job_id=job_id, kind=kind)


def _queued_events(committed_sessions):
    with committed_sessions() as db:
        return [row.payload for row in db.scalars(select(jobs_models.EventOutbox))]


def _audit(committed_sessions, action_id):
    with committed_sessions() as db:
        return list(db.scalars(select(audit_models.AuditLog).where(audit_models.AuditLog.action_id == action_id)))


def _gear_names(user_id):
    with core_database.SessionLocal() as db:
        return {gear.nickname for gear in gears_integration.get_gear_user(user_id, db)}


def _arrange_one_bike(strava):
    strava.on("GET", "/athlete", strava_factories.ok(strava_factories.athlete_payload(bikes=["b1"])))
    strava.on("GET", "/gear/b1", strava_factories.ok(strava_factories.gear_payload("b1")))


class TestRequestedOnTheDurableProfile:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """Every test in this class runs on the durable profile."""

    def test_a_gear_sync_is_staged_in_the_outbox_for_a_worker_and_nothing_runs_inline(
        self, committed_sessions, sign_in, user, strava
    ):
        response = sign_in(user).client.post(f"{_API}/strava/gear")

        assert response.status_code == 202, response.text
        assert (response.json()["kind"], response.json()["status"]) == ("strava_gear", "queued")
        (event,) = _queued_events(committed_sessions)
        assert (event["user_id"], event["kind"], event["job_id"]) == (str(user.id), "gear", response.json()["id"])
        assert strava.calls == []
        assert _audit(committed_sessions, _UNLINK_AUDIT) == [], "a gear sync is not audited"

    def test_an_unlink_is_staged_with_its_audit_row_in_the_same_commit(self, committed_sessions, sign_in, user):
        response = sign_in(user).client.post(f"{_API}/strava/unlink", json=_STEP_UP)

        assert response.status_code == 202, response.text
        (event,) = _queued_events(committed_sessions)
        assert event["kind"] == "unlink"
        (row,) = _audit(committed_sessions, _UNLINK_AUDIT)
        assert (row.outcome, row.actor_id, row.target_owner_id, row.details) == (
            "success",
            str(user.id),
            str(user.id),
            None,
        )

    def test_a_second_request_while_one_is_pending_is_a_conflict_that_stages_and_audits_nothing(
        self, committed_sessions, sign_in, user
    ):
        client = sign_in(user).client
        client.post(f"{_API}/strava/unlink", json=_STEP_UP)

        again = client.post(f"{_API}/strava/unlink", json=_STEP_UP)

        assert again.status_code == 409, again.text
        assert len(_queued_events(committed_sessions)) == 1
        assert len(_audit(committed_sessions, _UNLINK_AUDIT)) == 1

    def test_gear_and_unlink_do_not_block_each_other(self, sign_in, user):
        client = sign_in(user).client

        assert client.post(f"{_API}/strava/gear").status_code == 202
        assert client.post(f"{_API}/strava/unlink", json=_STEP_UP).status_code == 202

    def test_the_durable_handler_runs_the_staged_gear_sync_and_records_its_outcome(
        self, committed_sessions, sign_in, user, strava, states, rate_limits
    ):
        _arrange_one_bike(strava)
        job = sign_in(user).client.post(f"{_API}/strava/gear").json()
        (event,) = _queued_events(committed_sessions)

        strava_sync_service.run_sync(strava_events.SyncRequestedPayload.model_validate(event), states, rate_limits)

        assert _gear_names(user.id) == {"Road bike"}
        assert states.get(user.id, GEAR).status == Status.SUCCEEDED
        assert job["id"] == event["job_id"]


class TestDurableHandlers:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """The Strava handlers are registered with the durable-job registry."""

    def _event(self, user, job_id, kind=GEAR, *, retry_count=1, max_attempts=3):
        return Event(
            event_id=str(uuid.uuid4()),
            event_type=strava_events.STRAVA_SYNC_REQUESTED,
            source="test",
            timestamp="2026-01-01T00:00:00+00:00",
            payload=_payload(user, job_id, kind).model_dump(mode="json"),
            retry_count=retry_count,
            max_attempts=max_attempts,
        )

    def test_the_registered_handler_runs_the_sync_it_is_given(self, user, strava, states):
        _arrange_one_bike(strava)
        job = states.begin(user.id, GEAR, conflict="busy")
        handler = jobs_registry.registry.get(strava_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID)

        handler(self._event(user, job.id))

        assert states.get(user.id, GEAR).status == Status.SUCCEEDED
        assert _gear_names(user.id) == {"Road bike"}

    def test_a_failure_before_the_last_attempt_keeps_the_claim_for_the_retry_and_the_last_one_frees_it(
        self, user, strava, states
    ):
        strava.on("GET", "/athlete", strava_factories.refused(500))
        job = states.begin(user.id, GEAR, conflict="busy")
        handler = jobs_registry.registry.get(strava_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID)

        with pytest.raises(core_exceptions.DependencyFailedError):
            handler(self._event(user, job.id, retry_count=1))
        assert states.get(user.id, GEAR).status == Status.QUEUED
        with pytest.raises(core_exceptions.DependencyFailedError):
            handler(self._event(user, job.id, retry_count=3))

        assert states.get(user.id, GEAR).status == Status.FAILED

    def test_a_sync_the_runner_gave_up_on_is_closed_by_the_dead_letter_hook(self, user, states):
        job = states.begin(user.id, GEAR, conflict="busy")
        on_dead_letter = jobs_registry.registry.dead_letter_callback(strava_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID)

        on_dead_letter(self._event(user, job.id), "lease expired")

        assert states.get(user.id, GEAR).status == Status.FAILED
        states.begin(user.id, GEAR, conflict="busy")

    def test_the_module_registers_its_handler_with_the_composition_root(self):
        registry = JobHandlerRegistry()

        strava_subscriber_registry.register_durable_handlers(registry)

        assert registry.subscribers_for(strava_events.STRAVA_SYNC_REQUESTED) == (
            strava_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID,
        )


def test_the_link_and_sync_pools_stop_and_start_again_for_a_later_job():
    strava_integration.shutdown_pools()
    ran = threading.Event()

    strava_sync_service._sync_pool.submit(ran.set)
    strava_sync_service.shutdown_sync_pool(wait=True)

    assert ran.is_set()


class TestRequestedWithoutDurableJobs:
    def test_a_gear_sync_runs_on_the_in_process_pool_and_its_job_reports_the_outcome(
        self, committed_sessions, sign_in, user, strava
    ):
        _arrange_one_bike(strava)
        client = sign_in(user).client

        response = client.post(f"{_API}/strava/gear")
        strava_sync_service.shutdown_sync_pool(wait=True)

        assert response.status_code == 202, response.text
        assert _gear_names(user.id) == {"Road bike"}
        job = client.get(response.headers["Content-Location"])
        assert (job.status_code, job.json()["status"]) == (200, "succeeded")

    def test_an_unlink_runs_on_the_pool_and_is_audited_once_the_pool_took_it(
        self, committed_sessions, sign_in, user, strava
    ):
        strava.on("POST", "/oauth/deauthorize", strava_factories.ok({}))
        client = sign_in(user).client

        response = client.post(f"{_API}/strava/unlink", json=_STEP_UP)
        strava_sync_service.shutdown_sync_pool(wait=True)

        assert response.status_code == 202, response.text
        with committed_sessions() as db:
            stored = user_integrations_integration.require_user_integrations(user.id, db)
        assert stored.strava_token is None
        (row,) = _audit(committed_sessions, _UNLINK_AUDIT)
        assert (row.outcome, row.target_owner_id) == ("success", str(user.id))

    def test_an_unlink_whose_step_up_is_refused_queues_and_audits_nothing(
        self, committed_sessions, sign_in, user, strava
    ):
        _arrange_one_bike(strava)
        client = sign_in(user).client

        refused = client.post(f"{_API}/strava/unlink", json={"step_up": {"current_password": "wrong"}})
        queued_after = client.post(f"{_API}/strava/gear")
        strava_sync_service.shutdown_sync_pool(wait=True)

        assert refused.status_code in (401, 403), refused.text
        assert _audit(committed_sessions, _UNLINK_AUDIT) == []
        assert queued_after.status_code == 202

    def test_a_full_pool_refuses_the_unlink_without_auditing_it_and_frees_the_user_to_retry(
        self, committed_sessions, sign_in, user, strava
    ):
        release = threading.Event()
        for _ in range(core_attempt_capacity()):
            strava_sync_service._sync_pool.submit(release.wait)
        client = sign_in(user).client
        try:
            full = client.post(f"{_API}/strava/unlink", json=_STEP_UP)
        finally:
            release.set()
            strava_sync_service.shutdown_sync_pool(wait=True)

        assert full.status_code == 503, full.text
        assert _audit(committed_sessions, _UNLINK_AUDIT) == []
        strava.on("POST", "/oauth/deauthorize", strava_factories.ok({}))
        assert client.post(f"{_API}/strava/unlink", json=_STEP_UP).status_code == 202
        strava_sync_service.shutdown_sync_pool(wait=True)


def core_attempt_capacity() -> int:
    """How many jobs fill the in-process sync pool."""
    import core.sync_runner as core_sync_runner

    return core_sync_runner.MAX_PENDING_LOCAL_SYNCS


class TestRunSync:
    @pytest.fixture
    def job(self, states, user):
        return states.begin(user.id, GEAR, conflict="busy")

    def test_a_gear_sync_runs_and_completes(self, user, job, strava, states, rate_limits):
        _arrange_one_bike(strava)

        strava_sync_service.run_sync(_payload(user, job.id), states, rate_limits)

        assert states.get(user.id, GEAR).status == Status.SUCCEEDED
        assert _gear_names(user.id) == {"Road bike"}

    def test_a_gear_sync_for_an_account_that_is_not_linked_is_recorded_as_failed(self, states, rate_limits, db):
        unlinked = make_user(db)
        job = states.begin(unlinked.id, GEAR, conflict="busy")

        strava_sync_service.run_sync(_payload(unlinked, job.id), states, rate_limits)

        assert states.get(unlinked.id, GEAR).status == Status.FAILED

    def test_a_rate_limit_fails_the_sync_without_raising_so_nothing_retries_into_it(
        self, user, job, strava, states, rate_limits
    ):
        strava.on("GET", "/athlete", strava_factories.rate_limited())

        strava_sync_service.run_sync(_payload(user, job.id), states, rate_limits, will_retry=True)

        assert states.get(user.id, GEAR).status == Status.FAILED

    def test_a_failure_a_worker_will_retry_keeps_the_claim_held(self, user, job, strava, states, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_sync_service.run_sync(_payload(user, job.id), states, rate_limits, will_retry=True)

        assert states.get(user.id, GEAR).status == Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(user.id, GEAR, conflict="busy")

    def test_a_last_failure_is_recorded_and_frees_the_claim(self, user, job, strava, states, rate_limits):
        strava.on("GET", "/athlete", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_sync_service.run_sync(_payload(user, job.id), states, rate_limits, will_retry=False)

        assert states.get(user.id, GEAR).status == Status.FAILED
        states.begin(user.id, GEAR, conflict="busy")

    def test_an_unlink_runs_and_completes_even_when_strava_was_not_linked(self, states, rate_limits, db):
        unlinked = make_user(db)
        job = states.begin(unlinked.id, UNLINK, conflict="busy")

        strava_sync_service.run_sync(_payload(unlinked, job.id, UNLINK), states, rate_limits)

        assert states.get(unlinked.id, UNLINK).status == Status.SUCCEEDED

    def test_a_link_is_never_run_as_a_sync_job_and_leaves_the_link_state_alone(self, user, states, rate_limits):
        job = states.begin(user.id, strava_constants.SyncKind.LINK, conflict="busy")

        with pytest.raises(ValueError, match="link"):
            strava_sync_service.run_sync(_payload(user, job.id, strava_constants.SyncKind.LINK), states, rate_limits)

        assert states.get(user.id, strava_constants.SyncKind.LINK).status == Status.QUEUED


class TestDeadLetter:
    def test_a_pending_sync_is_closed_so_the_user_can_queue_another(self, user, states):
        job = states.begin(user.id, GEAR, conflict="busy")

        strava_sync_service.close_dead_lettered_sync(_payload(user, job.id), states)

        assert states.get(user.id, GEAR).status == Status.FAILED
        states.begin(user.id, GEAR, conflict="busy")

    def test_a_finished_sync_is_left_as_it_is(self, user, states):
        job = states.begin(user.id, GEAR, conflict="busy")
        states.set_status(user.id, GEAR, Status.SUCCEEDED, job_id=job.id)

        strava_sync_service.close_dead_lettered_sync(_payload(user, job.id), states)

        assert states.get(user.id, GEAR).status == Status.SUCCEEDED

    def test_a_sync_a_newer_one_superseded_is_left_alone(self, user, states):
        old = states.begin(user.id, GEAR, conflict="busy")
        states.set_status(user.id, GEAR, Status.FAILED, job_id=old.id)
        states.begin(user.id, GEAR, conflict="busy")

        strava_sync_service.close_dead_lettered_sync(_payload(user, old.id), states)

        assert states.get(user.id, GEAR).status == Status.QUEUED

    def test_a_sync_whose_state_expired_is_left_alone(self, user, states, advance_state_clock):
        job = states.begin(user.id, GEAR, conflict="busy")
        advance_state_clock(core_attempt_state.SYNC_TTL_SECONDS + 1)

        strava_sync_service.close_dead_lettered_sync(_payload(user, job.id), states)

        assert states.get(user.id, GEAR) is None


class TestReadSyncJob:
    def test_the_current_job_reads_with_its_id_and_kind(self, user, states):
        job = states.begin(user.id, GEAR, conflict="busy")

        status = strava_integration.read_sync_job(job, platform_runtime.get_state())

        assert (status.id, status.kind, status.status) == (job.id, "strava_gear", Status.QUEUED)

    def test_a_finished_job_reads_with_its_outcome(self, user, states):
        job = states.begin(user.id, GEAR, conflict="busy")
        states.set_status(user.id, GEAR, Status.SUCCEEDED, job_id=job.id)

        assert strava_integration.read_sync_job(job, platform_runtime.get_state()).status == Status.SUCCEEDED

    def test_a_job_replaced_by_a_later_sync_of_its_kind_reads_as_none(self, user, states):
        old = states.begin(user.id, GEAR, conflict="busy")
        states.set_status(user.id, GEAR, Status.SUCCEEDED, job_id=old.id)
        states.begin(user.id, GEAR, conflict="busy")

        assert strava_integration.read_sync_job(old, platform_runtime.get_state()) is None

    def test_an_expired_job_reads_as_none(self, user, states, advance_state_clock):
        job = states.begin(user.id, GEAR, conflict="busy")
        advance_state_clock(core_attempt_state.SYNC_TTL_SECONDS + 1)

        assert strava_integration.read_sync_job(job, platform_runtime.get_state()) is None


class TestActivityRange:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """The range job is staged for a worker, so it does not run on a thread while the test reads it."""

    def _today(self):
        import core.timezone as core_timezone

        return core_timezone.today_in(core_timezone.or_default(None))

    def test_a_range_is_queued_as_a_job_of_whole_days(self, sign_in, user, committed_sessions):
        today = self._today()
        start, end = today - timedelta(days=3), today - timedelta(days=1)

        response = sign_in(user).client.post(
            f"{_API}/strava/activities", params={"start_date": start.isoformat(), "end_date": end.isoformat()}
        )

        assert response.status_code == 202, response.text
        body = response.json()
        assert (body["kind"], body["provider"]) == ("activity_refresh", "strava")
        with committed_sessions() as db:
            row = db.get(activity_ingestion_models.ActivityIngestionJob, uuid.UUID(body["id"]))
        assert (row.window_start.date(), row.window_start.hour) == (start, 0)
        assert (row.window_end.date(), row.window_end.hour, row.window_end.minute) == (end, 23, 59)
        assert response.headers["Content-Location"].endswith(body["id"])

    def test_a_range_ending_in_the_future_is_refused(self, sign_in, user):
        end = self._today() + timedelta(days=1)

        response = sign_in(user).client.post(
            f"{_API}/strava/activities", params={"start_date": self._today().isoformat(), "end_date": end.isoformat()}
        )

        assert response.status_code == 400, response.text

    def test_a_reversed_range_is_refused(self, sign_in, user):
        today = self._today()

        response = sign_in(user).client.post(
            f"{_API}/strava/activities",
            params={"start_date": today.isoformat(), "end_date": (today - timedelta(days=2)).isoformat()},
        )

        assert response.status_code == 422, response.text

    def test_a_range_longer_than_the_cap_is_refused_and_one_at_the_cap_is_queued(self, sign_in, user):
        import core.sync_runner as core_sync_runner

        last = self._today() - timedelta(days=1)
        cap = core_sync_runner.MAX_ACTIVITIES_RANGE_DAYS
        client = sign_in(user).client

        too_long = client.post(
            f"{_API}/strava/activities",
            params={"start_date": (last - timedelta(days=cap)).isoformat(), "end_date": last.isoformat()},
        )
        at_the_cap = client.post(
            f"{_API}/strava/activities",
            params={"start_date": (last - timedelta(days=cap - 1)).isoformat(), "end_date": last.isoformat()},
        )

        assert (too_long.status_code, at_the_cap.status_code) == (400, 202)
