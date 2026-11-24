"""Queueing and running Garmin Connect gear and health syncs, on the real database and platform state."""

import threading
import uuid
from datetime import date, timedelta

import garminconnect
import jasil.runtime as jasil_runtime
import pytest
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from sqlalchemy import select

import core.attempt_state as core_attempt_state
import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.timezone as core_timezone
import modules.activities.activity_ingestion.models as ingestion_models
import modules.garmin.constants as garmin_constants
import modules.garmin.events as garmin_events
import modules.garmin.integration_service as garmin_integration
import modules.garmin.subscribers as garmin_subscribers
import modules.garmin.sync_service as garmin_sync_service
import modules.gears.gear.models as gear_models
import modules.health.health_steps.models as steps_models
from tests._factories import garmin as garmin_factories
from tests.garmin.conftest import stored_token

Kind = garmin_constants.SyncKind
Status = garmin_constants.SyncStatus


def _today() -> date:
    """The day the tests' users (UTC) are in, read from the platform clock as the code reads it."""
    return core_timezone.today_in(core_timezone.or_default("UTC"))


@pytest.fixture
def durable(monkeypatch) -> list[Event]:
    """Switch durable jobs on and collect the ``garmin.sync_requested`` events published for a worker."""
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    events: list[Event] = []
    jasil_runtime.get_active_platform().events.subscribe(garmin_events.GARMIN_SYNC_REQUESTED, events.append)
    return events


def _gear_job(sync_states, user, **payload) -> garmin_events.SyncRequestedPayload:
    job = sync_states.begin(user.id, Kind.GEAR, conflict="busy")
    return garmin_events.SyncRequestedPayload(user_id=user.id, job_id=job.id, kind=Kind.GEAR, **payload)


def _health_job(sync_states, user, start: date, end: date) -> garmin_events.SyncRequestedPayload:
    job = sync_states.begin(user.id, Kind.HEALTH, conflict="busy")
    return garmin_events.SyncRequestedPayload(
        user_id=user.id, job_id=job.id, kind=Kind.HEALTH, start_date=start, end_date=end
    )


def _request_gear(sessions, user, sync_states, rate_limits):
    with sessions() as db:
        return garmin_sync_service.request_gear_sync(user.id, sync_states, rate_limits, db)


def _request_health(sessions, user, start: date, end: date, sync_states, rate_limits):
    with sessions() as db:
        return garmin_sync_service.request_health_sync(user.id, start, end, sync_states, rate_limits, db)


class TestRequestWithoutDurableJobs:
    def test_a_gear_sync_is_queued_runs_on_the_pool_and_records_its_outcome(
        self, account, linked, sync_states, rate_limits, committed_sessions, sync_pool, hints
    ):
        account.gear = [garmin_factories.gear_payload("g-1")]
        running, release = threading.Event(), threading.Event()

        def hold_the_sync(method):
            if method == "get_device_last_used":
                running.set()
                release.wait(10)

        account.on_call = hold_the_sync

        queued = _request_gear(committed_sessions, linked, sync_states, rate_limits)

        assert running.wait(10)
        assert (queued.kind, queued.status) == ("garmin_sync_gear", Status.QUEUED)
        assert sync_states.get(linked.id, Kind.GEAR).status == Status.RUNNING
        release.set()
        sync_pool.shutdown(wait=True)
        assert sync_states.get(linked.id, Kind.GEAR).status == Status.SUCCEEDED
        with committed_sessions() as db:
            assert db.scalars(select(gear_models.Gear.garminconnect_gear_id)).all().count("g-1") == 1
        assert "GEARS_CHANGED" in [hint.get("message") for _, hint in hints]

    def test_a_sync_waiting_for_a_worker_is_recorded_queued(
        self, linked, sync_states, rate_limits, committed_sessions, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(3))

        _request_gear(committed_sessions, linked, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.QUEUED

    def test_a_second_sync_of_a_kind_while_one_is_pending_is_a_conflict(
        self, linked, sync_states, rate_limits, committed_sessions, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(5))
        _request_gear(committed_sessions, linked, sync_states, rate_limits)

        with pytest.raises(core_exceptions.ConflictError):
            _request_gear(committed_sessions, linked, sync_states, rate_limits)

    def test_other_kinds_and_other_users_are_not_blocked(
        self, linked, make_linked, sync_states, rate_limits, committed_sessions, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(6))
        other = make_linked()
        _request_gear(committed_sessions, linked, sync_states, rate_limits)

        _request_health(committed_sessions, linked, _today(), _today(), sync_states, rate_limits)
        _request_gear(committed_sessions, other, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.HEALTH).status == Status.QUEUED
        assert sync_states.get(other.id, Kind.GEAR).status == Status.QUEUED

    def test_a_sync_that_cannot_be_queued_does_not_block_a_retry(
        self, linked, sync_states, rate_limits, committed_sessions, closed_pool, sync_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", closed_pool)
        with pytest.raises(RuntimeError):
            _request_gear(committed_sessions, linked, sync_states, rate_limits)
        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", sync_pool)

        _request_gear(committed_sessions, linked, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.GEAR).status in {Status.QUEUED, Status.RUNNING, Status.FAILED}

    def test_the_pool_refuses_syncs_beyond_its_limit_and_the_sync_is_recorded_failed(
        self, linked, sync_states, rate_limits, committed_sessions, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(1))

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            _request_gear(committed_sessions, linked, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED


class TestRequestWithDurableJobs:
    def test_a_health_sync_is_published_for_a_worker_and_not_run_here(
        self, account, linked, sync_states, rate_limits, committed_sessions, durable
    ):
        today = _today()

        result = _request_health(committed_sessions, linked, today - timedelta(days=2), today, sync_states, rate_limits)

        [event] = durable
        assert event.source == garmin_constants.SYNC_SOURCE_API
        assert event.payload == {
            "user_id": str(linked.id),
            "job_id": str(result.id),
            "kind": "health",
            "start_date": (today - timedelta(days=2)).isoformat(),
            "end_date": today.isoformat(),
        }
        assert result.status == Status.QUEUED
        assert sync_states.get(linked.id, Kind.HEALTH).status == Status.QUEUED
        assert account.calls == []

    def test_a_second_sync_of_a_kind_while_one_is_pending_is_a_conflict_and_publishes_nothing_more(
        self, linked, sync_states, rate_limits, committed_sessions, durable
    ):
        _request_gear(committed_sessions, linked, sync_states, rate_limits)

        with pytest.raises(core_exceptions.ConflictError):
            _request_gear(committed_sessions, linked, sync_states, rate_limits)

        assert len(durable) == 1


class TestRequestRanges:
    def test_a_health_range_beyond_the_cap_is_refused_and_nothing_is_queued(
        self, linked, sync_states, rate_limits, committed_sessions, durable
    ):
        today = _today()
        too_long = today - timedelta(days=garmin_constants.MAX_HEALTH_RANGE_DAYS)

        with pytest.raises(core_exceptions.InvalidInputError):
            _request_health(committed_sessions, linked, too_long, today, sync_states, rate_limits)

        assert durable == []
        assert sync_states.get(linked.id, Kind.HEALTH) is None

    def test_the_longest_allowed_health_range_is_accepted(
        self, linked, sync_states, rate_limits, committed_sessions, durable
    ):
        today = _today()
        longest = today - timedelta(days=garmin_constants.MAX_HEALTH_RANGE_DAYS - 1)

        _request_health(committed_sessions, linked, longest, today, sync_states, rate_limits)

        assert len(durable) == 1

    def test_a_range_ending_after_the_users_today_is_refused(
        self, linked, sync_states, rate_limits, committed_sessions, durable
    ):
        tomorrow = _today() + timedelta(days=1)

        with pytest.raises(core_exceptions.InvalidInputError, match="future"):
            _request_health(committed_sessions, linked, _today(), tomorrow, sync_states, rate_limits)

        assert durable == []

    def test_an_activities_range_beyond_the_cap_is_refused_and_no_job_is_created(self, linked, committed_sessions):
        with (
            committed_sessions() as db,
            pytest.raises(core_exceptions.InvalidInputError, match="must not exceed"),
        ):
            garmin_sync_service.request_activities_sync(
                linked.id, date(2010, 1, 1), _today(), jasil_runtime.get_active_platform().storage, db
            )

        with committed_sessions() as db:
            assert db.scalars(select(ingestion_models.ActivityIngestionJob)).all() == []

    def test_an_activities_range_ending_after_the_users_today_is_refused(self, linked, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.InvalidInputError, match="future"):
            garmin_sync_service.request_activities_sync(
                linked.id, _today(), _today() + timedelta(days=1), jasil_runtime.get_active_platform().storage, db
            )


class TestReadSyncJob:
    def test_a_job_reads_with_its_id_and_kind(self, unlinked, sync_states):
        job = sync_states.begin(unlinked.id, Kind.HEALTH, conflict="busy")

        read = garmin_integration.read_sync_job(job, jasil_runtime.get_state())

        assert (read.id, read.kind, read.status) == (job.id, "garmin_sync_health", Status.QUEUED)

    def test_an_earlier_job_reads_as_gone_once_the_next_one_started(self, unlinked, sync_states):
        first = sync_states.begin(unlinked.id, Kind.GEAR, conflict="busy")
        sync_states.set_status(unlinked.id, Kind.GEAR, Status.SUCCEEDED, job_id=first.id)
        second = sync_states.begin(unlinked.id, Kind.GEAR, conflict="busy")
        state = jasil_runtime.get_state()

        assert garmin_integration.read_sync_job(first, state) is None
        assert garmin_integration.read_sync_job(second, state).id == second.id

    def test_an_expired_job_reads_as_gone(self, unlinked, sync_states):
        job = sync_states.begin(unlinked.id, Kind.GEAR, conflict="busy")
        jasil_runtime.get_state().delete(core_attempt_state.key("garmin", "sync:state", job.subject))

        assert garmin_integration.read_sync_job(job, jasil_runtime.get_state()) is None


class TestRunSync:
    def test_a_gear_sync_stores_the_gear_and_a_health_sync_the_days_and_each_tells_the_browser_what_to_refetch(
        self, account, linked, make_linked, sync_states, rate_limits, committed_sessions, hints
    ):
        other = make_linked()
        account.gear = [garmin_factories.gear_payload("g-1")]
        account.daily_steps = [garmin_factories.steps_entry(_today().isoformat(), 4200)]
        gear = _gear_job(sync_states, linked)
        health = _health_job(sync_states, other, _today(), _today())

        garmin_sync_service.run_sync(gear, sync_states, rate_limits)
        garmin_sync_service.run_sync(health, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.SUCCEEDED
        assert sync_states.get(other.id, Kind.HEALTH).status == Status.SUCCEEDED
        with committed_sessions() as db:
            assert db.scalars(
                select(steps_models.HealthSteps.steps).where(steps_models.HealthSteps.user_id == other.id)
            ).all() == [4200]
        messages = [
            (key, hint["message"], hint.get("kind"))
            for key, hint in hints
            if hint["message"] in {"JOB_STATUS_CHANGED", "GEARS_CHANGED", "HEALTH_CHANGED"}
        ]
        assert [(message, kind) for _, message, kind in messages if _.endswith(str(linked.id))] == [
            ("JOB_STATUS_CHANGED", "garmin_sync_gear"),
            ("GEARS_CHANGED", None),
        ]
        assert [(message, kind) for _, message, kind in messages if _.endswith(str(other.id))] == [
            ("JOB_STATUS_CHANGED", "garmin_sync_health"),
            ("HEALTH_CHANGED", None),
        ]

    def test_a_sync_that_did_not_run_is_failed_announces_its_job_but_not_a_refetch_and_releases_its_claim(
        self, account, unlinked, sync_states, rate_limits, hints
    ):
        job = _gear_job(sync_states, unlinked)

        garmin_sync_service.run_sync(job, sync_states, rate_limits)

        assert sync_states.get(unlinked.id, Kind.GEAR).status == Status.FAILED
        assert [hint["message"] for _, hint in hints] == ["JOB_STATUS_CHANGED"]
        sync_states.begin(unlinked.id, Kind.GEAR, conflict="busy")

    def test_a_failure_nothing_retries_is_recorded_released_and_raised(self, account, linked, sync_states, rate_limits):
        account.fail("get_device_last_used", RuntimeError("boom"))
        job = _gear_job(sync_states, linked)

        with pytest.raises(RuntimeError):
            garmin_sync_service.run_sync(job, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED
        sync_states.begin(linked.id, Kind.GEAR, conflict="busy")

    def test_a_failure_with_attempts_left_stays_queued_and_claimed_for_its_retry(
        self, account, linked, sync_states, rate_limits
    ):
        account.fail("get_device_last_used", RuntimeError("boom"))
        job = _gear_job(sync_states, linked)

        with pytest.raises(RuntimeError):
            garmin_sync_service.run_sync(job, sync_states, rate_limits, will_retry=True)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            sync_states.begin(linked.id, Kind.GEAR, conflict="busy")

    def test_a_rate_limited_sync_is_failed_without_a_retry_and_records_the_limit_for_every_replica(
        self, account, linked, sync_states, rate_limits
    ):
        account.fail("get_device_last_used", garminconnect.GarminConnectTooManyRequestsError("429"))
        job = _gear_job(sync_states, linked)

        garmin_sync_service.run_sync(job, sync_states, rate_limits, will_retry=True)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED
        assert rate_limits.rate_limited_until(linked.id) is not None
        sync_states.begin(linked.id, Kind.GEAR, conflict="busy")

    def test_a_sync_refused_by_an_active_limit_is_failed_without_a_retry_or_a_call_to_garmin(
        self, account, linked, sync_states, rate_limits
    ):
        until = rate_limits.mark_rate_limited(linked.id)
        job = _gear_job(sync_states, linked)

        garmin_sync_service.run_sync(job, sync_states, rate_limits, will_retry=True)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED
        assert rate_limits.rate_limited_until(linked.id) == until
        assert account.clients == []

    def test_a_rejected_token_unlinks_the_account_and_the_sync_is_failed(
        self, account, linked, sync_states, rate_limits, committed_sessions
    ):
        account.fail("get_device_last_used", garminconnect.GarminConnectAuthenticationError("401"))
        job = _gear_job(sync_states, linked)

        garmin_sync_service.run_sync(job, sync_states, rate_limits)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED
        assert stored_token(committed_sessions, linked.id) is None

    def test_a_health_payload_needs_a_date_range(self, unlinked):
        with pytest.raises(ValueError):
            garmin_events.SyncRequestedPayload(user_id=unlinked.id, job_id=uuid.uuid4(), kind=Kind.HEALTH)


class TestDurableHandler:
    @staticmethod
    def _event(job: garmin_events.SyncRequestedPayload, retry_count: int, max_attempts: int | None = 3) -> Event:
        return Event(
            event_id="evt-1",
            event_type=garmin_events.GARMIN_SYNC_REQUESTED,
            source="test",
            timestamp="2026-10-31T00:00:00+00:00",
            payload=job.model_dump(mode="json"),
            retry_count=retry_count,
            max_attempts=max_attempts,
        )

    @staticmethod
    def _registry() -> JobHandlerRegistry:
        registry = JobHandlerRegistry()
        garmin_subscribers.register_durable_handlers(registry)
        return registry

    def test_the_handler_runs_the_sync_over_the_platform_state(self, account, linked, sync_states, committed_sessions):
        account.gear = [garmin_factories.gear_payload("g-1")]
        job = _gear_job(sync_states, linked)

        self._registry().get(garmin_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID)(self._event(job, 1))

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.SUCCEEDED
        with committed_sessions() as db:
            assert db.scalars(select(gear_models.Gear.garminconnect_gear_id)).all().count("g-1") == 1

    @pytest.mark.parametrize(("retry_count", "status"), [(1, Status.QUEUED), (2, Status.QUEUED), (3, Status.FAILED)])
    def test_a_failed_sync_is_asked_to_retry_only_while_attempts_remain(
        self, account, linked, sync_states, retry_count, status
    ):
        account.fail("get_device_last_used", RuntimeError("boom"))
        job = _gear_job(sync_states, linked)

        with pytest.raises(RuntimeError):
            self._registry().get(garmin_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID)(self._event(job, retry_count))

        assert sync_states.get(linked.id, Kind.GEAR).status == status

    def test_the_handler_is_registered_with_the_dead_letter_callback(self):
        assert self._registry().dead_letter_subscriber_ids() == {garmin_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID}


class TestDeadLetter:
    """A sync the runner gave up on ends as failed, however its last attempt ended."""

    @staticmethod
    def _dead_letter(job: garmin_events.SyncRequestedPayload, error: str | None) -> None:
        registry = JobHandlerRegistry()
        garmin_subscribers.register_durable_handlers(registry)
        event = TestDurableHandler._event(job, 3)
        registry.dead_letter_callback(garmin_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID)(event, error)

    @pytest.mark.parametrize("status", [Status.QUEUED, Status.RUNNING])
    def test_a_pending_sync_is_failed_and_its_claim_released(self, linked, sync_states, status):
        job = _gear_job(sync_states, linked)
        sync_states.set_status(linked.id, Kind.GEAR, status, job_id=job.job_id)

        self._dead_letter(job, "lease expired")

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.FAILED
        sync_states.begin(linked.id, Kind.GEAR, conflict="busy")

    def test_a_sync_that_already_finished_is_left_alone(self, linked, sync_states):
        job = _gear_job(sync_states, linked)
        sync_states.set_status(linked.id, Kind.GEAR, Status.SUCCEEDED, job_id=job.job_id)

        self._dead_letter(job, None)

        assert sync_states.get(linked.id, Kind.GEAR).status == Status.SUCCEEDED

    def test_an_expired_state_is_not_resurrected(self, linked, sync_states):
        job = garmin_events.SyncRequestedPayload(user_id=linked.id, job_id=uuid.uuid4(), kind=Kind.GEAR)

        self._dead_letter(job, None)

        assert sync_states.get(linked.id, Kind.GEAR) is None

    def test_a_sync_a_newer_one_superseded_is_left_alone(self, linked, sync_states):
        old = _gear_job(sync_states, linked)
        jasil_runtime.get_state().delete(
            core_attempt_state.key("garmin", "sync:claim", f"{linked.id}:{Kind.GEAR.value}")
        )
        newer = sync_states.begin(linked.id, Kind.GEAR, conflict="busy")

        garmin_sync_service.close_dead_lettered_sync(old, sync_states)

        assert sync_states.get(linked.id, Kind.GEAR, job_id=newer.id).status == Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            sync_states.begin(linked.id, Kind.GEAR, conflict="busy")


class _WaitProbePool(core_local_pool.BoundedPool):
    """A pool that records how many database connections are checked out when a submitter starts to wait."""

    def __init__(self) -> None:
        super().__init__("test-garmin-probe", workers=2, max_pending=10)
        self.checked_out: list[int] = []

    def submit_waiting(self, wait_seconds, run, /, *args, **kwargs):
        self.checked_out.append(core_database.engine.pool.checkedout())
        return super().submit_waiting(wait_seconds, run, *args, **kwargs)


class _FirstSubmitFails(core_local_pool.BoundedPool):
    """A pool that refuses its first job with a bug-like error and accepts the rest."""

    def __init__(self) -> None:
        super().__init__("test-garmin-flaky", workers=1, max_pending=10)
        self.refused = False

    def submit_waiting(self, wait_seconds, run, /, *args, **kwargs):
        if not self.refused:
            self.refused = True
            raise RuntimeError("cannot schedule")
        return super().submit_waiting(wait_seconds, run, *args, **kwargs)


class TestRecentHealth:
    def test_with_durable_jobs_each_linked_user_is_queued_for_a_worker_in_pages(
        self, linked, make_linked, unlinked, sync_states, rate_limits, durable, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_USERS_PAGE_SIZE", 2)
        users = [linked, make_linked(), make_linked()]

        garmin_sync_service.sync_recent_health(sync_states, rate_limits)

        assert sorted(event.payload["user_id"] for event in durable) == sorted(str(user.id) for user in users)
        assert str(unlinked.id) not in {event.payload["user_id"] for event in durable}

    def test_the_window_is_the_users_local_yesterday_and_today_and_the_scheduler_is_the_source(
        self, linked, sync_states, rate_limits, durable
    ):
        garmin_sync_service.sync_recent_health(sync_states, rate_limits)

        [event] = durable
        assert (event.payload["start_date"], event.payload["end_date"]) == (
            (_today() - timedelta(days=1)).isoformat(),
            _today().isoformat(),
        )
        assert event.source == garmin_constants.SYNC_SOURCE_SCHEDULER

    def test_a_user_with_a_pending_sync_is_skipped(self, linked, make_linked, sync_states, rate_limits, durable):
        other = make_linked()
        sync_states.begin(linked.id, Kind.HEALTH, conflict="busy")

        garmin_sync_service.sync_recent_health(sync_states, rate_limits)

        assert [event.payload["user_id"] for event in durable] == [str(other.id)]

    def test_without_durable_jobs_each_user_goes_to_the_pool_not_the_scheduler_thread(
        self, account, linked, make_linked, sync_states, rate_limits, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(5))
        users = [linked, make_linked()]

        garmin_sync_service.sync_recent_health(sync_states, rate_limits)

        assert [sync_states.get(user.id, Kind.HEALTH).status for user in users] == [Status.QUEUED, Status.QUEUED]
        assert account.calls == []

    def test_no_connection_is_held_while_waiting_for_a_pool_slot(
        self, account, linked, sync_states, rate_limits, monkeypatch, committed_sessions
    ):
        pool = _WaitProbePool()
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", pool)

        try:
            garmin_sync_service.sync_recent_health(sync_states, rate_limits)
        finally:
            pool.shutdown(wait=True)

        assert pool.checked_out == [0]

    def test_a_pool_that_stays_full_ends_the_pass(
        self, linked, make_linked, sync_states, rate_limits, blocked_pool, monkeypatch
    ):
        monkeypatch.setattr(garmin_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 0.01)
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", blocked_pool.with_held_worker(1))
        first, second = sorted([linked, make_linked()], key=lambda user: user.id)

        garmin_sync_service.sync_recent_health(sync_states, rate_limits)

        assert sync_states.get(first.id, Kind.HEALTH).status == Status.FAILED
        assert sync_states.get(second.id, Kind.HEALTH) is None

    def test_a_user_waits_for_a_slot_to_free_instead_of_being_skipped(
        self, account, linked, sync_states, rate_limits, blocked_pool, monkeypatch
    ):
        pool = blocked_pool.with_held_worker(1)
        monkeypatch.setattr(garmin_constants, "SCHEDULED_SLOT_WAIT_SECONDS", 10)
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", pool)
        threading.Timer(0.05, blocked_pool.release.set).start()

        garmin_sync_service.sync_recent_health(sync_states, rate_limits)
        pool.shutdown(wait=True)

        assert sync_states.get(linked.id, Kind.HEALTH).status == Status.SUCCEEDED

    def test_one_user_failing_does_not_stop_the_rest(
        self, account, linked, make_linked, sync_states, rate_limits, monkeypatch, caplog
    ):
        pool = _FirstSubmitFails()
        monkeypatch.setattr(garmin_sync_service, "_sync_pool", pool)
        first, second = sorted([linked, make_linked()], key=lambda user: user.id)

        try:
            garmin_sync_service.sync_recent_health(sync_states, rate_limits)
        finally:
            pool.shutdown(wait=True)

        assert sync_states.get(first.id, Kind.HEALTH).status == Status.FAILED
        assert sync_states.get(second.id, Kind.HEALTH).status != Status.FAILED
        assert "Error syncing recent Garmin Connect health data for user" in caplog.text
