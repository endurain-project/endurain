"""Tests for core.scheduler: the real APScheduler, the job registry and the cross-replica run-once guards."""

import asyncio
import contextlib
import dataclasses
import datetime
import logging
import threading
from types import SimpleNamespace

import jasil.audit as jasil_audit
import jasil.retention as platform_retention
import jasil.runtime as platform_runtime
import psycopg.errors
import pytest
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from jasil.backends.lock_pg import PgAdvisoryLock
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.exc import IntegrityError, OperationalError

import core.database as core_database
import core.scheduler as core_scheduler
from tests._helpers import database as test_database


def test_the_scheduler_runs_in_utc_whatever_the_host_zone():
    assert core_scheduler.scheduler.timezone == datetime.UTC


@pytest.fixture
async def scheduler():
    """The process's scheduler, stopped and emptied before and after the test."""
    core_scheduler.stop_scheduler()
    core_scheduler.scheduler.remove_all_jobs()
    yield core_scheduler.scheduler
    core_scheduler.stop_scheduler()
    core_scheduler.scheduler.remove_all_jobs()


@pytest.fixture
async def paused(scheduler):
    """The scheduler running without firing anything, so registered jobs are inspected, not executed."""
    scheduler.start(paused=True)
    return scheduler


@pytest.fixture(autouse=True)
def advisory_locks(committed_sessions):
    """Coordinate through PostgreSQL advisory locks, as a deployment with replicas does."""
    platform_runtime.set_active_platform(dataclasses.replace(_platform(), lock=PgAdvisoryLock(core_database.engine)))


@pytest.fixture
def clock(monkeypatch):
    """A clock the test moves: the scheduler's own, and the state backend's that expires the run marks."""
    import jasil.backends.state_memory as state_memory

    now = [1000.0]
    fake = SimpleNamespace(monotonic=lambda: now[0])
    monkeypatch.setattr(core_scheduler, "time", fake)
    monkeypatch.setattr(state_memory, "time", fake)

    def advance(seconds: float) -> None:
        now[0] += seconds

    return advance


def _platform():
    return platform_runtime.get_active_platform()


@contextlib.contextmanager
def _held_by_another_replica(lock_name: str):
    """Hold a coordination lock from another thread, as another replica's scheduler does."""
    acquired, release = threading.Event(), threading.Event()

    def hold():
        with _platform().lock.try_acquire(lock_name):
            acquired.set()
            release.wait(timeout=30)

    thread = threading.Thread(target=hold)
    thread.start()
    assert acquired.wait(timeout=30)
    try:
        yield
    finally:
        release.set()
        thread.join()


def _mark(lock_name: str):
    return _platform().state.get(f"endurain:scheduler:last-run:{lock_name}")


class Recorder:
    """A scheduled operation that records its calls."""

    def __init__(self, *outcomes) -> None:
        self.calls: list[tuple] = []
        self.outcomes = list(outcomes)

    def __call__(self, *args):
        self.calls.append(args)
        outcome = self.outcomes.pop(0) if self.outcomes else "ran"
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class AsyncRecorder(Recorder):
    """An asynchronous scheduled operation: pass ``run``, a coroutine function that records its calls."""

    async def run(self, *args):
        return self(*args)


class TestSchedulerJobId:
    def test_generates_stable_id_from_description(self):
        assert (
            core_scheduler._scheduler_job_id("refresh Strava user tokens every 60 minutes")
            == "endurain_refresh_strava_user_tokens_every_60_minutes"
        )

    def test_handles_single_word_description(self):
        assert core_scheduler._scheduler_job_id("test") == "endurain_test"


class TestStartScheduler:
    async def test_starts_the_scheduler_and_the_one_shot_jobs_run_to_completion(self, scheduler):
        finished = asyncio.Event()
        outcomes: list[object] = []

        def listener(event):
            outcomes.append(event)
            if len(outcomes) == 2:
                finished.set()

        scheduler.add_listener(listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

        core_scheduler.start_scheduler()
        await asyncio.wait_for(finished.wait(), timeout=30)

        assert scheduler.running
        assert {event.job_id for event in outcomes} == {
            "endurain_prune_expired_records_oneshot",
            "endurain_audit_maintenance_oneshot",
        }
        assert all(event.exception is None for event in outcomes)

    async def test_an_already_running_scheduler_is_left_running_and_given_the_jobs(self, paused):
        core_scheduler.start_scheduler([core_scheduler.ScheduledJob(print, 5, "a")])

        assert paused.running
        assert paused.get_job("endurain_a") is not None

    async def test_every_job_it_is_handed_is_registered_with_its_interval(self, paused):
        core_scheduler.start_scheduler(
            [core_scheduler.ScheduledJob(print, 5, "a"), core_scheduler.ScheduledJob(print, 10, "b")]
        )

        intervals = {
            job.id: job.trigger.interval.total_seconds() for job in paused.get_jobs() if "oneshot" not in job.id
        }
        assert intervals == {"endurain_a": 300, "endurain_b": 600}

    async def test_handed_nothing_it_registers_only_the_one_shot_jobs(self, paused):
        core_scheduler.start_scheduler()

        assert {job.id for job in paused.get_jobs()} == {
            "endurain_prune_expired_records_oneshot",
            "endurain_audit_maintenance_oneshot",
        }

    async def test_a_locked_sync_job_runs_once_per_interval_across_replicas(self, paused):
        operation = Recorder()
        core_scheduler.start_scheduler([core_scheduler.ScheduledJob(operation, 5, "locked", [1], "provider_sync")])
        job = paused.get_job("endurain_locked")

        assert job.func(*job.args) == "ran"
        assert job.func(*job.args) is None
        assert operation.calls == [(1,)]

    async def test_a_locked_async_job_runs_once_per_interval_across_replicas(self, paused):
        operation = AsyncRecorder()
        core_scheduler.start_scheduler([core_scheduler.ScheduledJob(operation.run, 5, "locked", [1], "provider_async")])
        job = paused.get_job("endurain_locked")

        assert await job.func(*job.args) == "ran"
        assert await job.func(*job.args) is None
        assert operation.calls == [(1,)]

    async def test_a_job_without_a_lock_runs_on_every_tick(self, paused):
        operation = Recorder()
        core_scheduler.start_scheduler([core_scheduler.ScheduledJob(operation, 5, "unlocked", [2])])
        job = paused.get_job("endurain_unlocked")

        job.func(*job.args)
        job.func(*job.args)

        assert operation.calls == [(2,), (2,)]


class TestPlatformJobs:
    def test_maintains_the_audit_trail_every_five_minutes(self):
        jobs = {job.func: job for job in core_scheduler.platform_jobs()}

        assert jobs[jasil_audit.run_audit_maintenance].minutes == 5
        # The substrate takes its own lock; a scheduler lock would only add a second one.
        assert jobs[jasil_audit.run_audit_maintenance].lock_name is None

    def test_prunes_the_platform_bookkeeping_daily(self):
        jobs = {job.func: job for job in core_scheduler.platform_jobs()}

        assert jobs[platform_retention.prune_expired_records].minutes == 1440


class TestAddSchedulerJob:
    async def test_the_job_is_registered_under_its_stable_id_and_replaced_on_a_second_add(self, paused):
        core_scheduler.add_scheduler_job(print, "interval", 60, [True], "test job every 60 minutes")
        core_scheduler.add_scheduler_job(print, "interval", 30, [False], "test job every 60 minutes")

        (job,) = paused.get_jobs()
        assert job.id == "endurain_test_job_every_60_minutes"
        assert job.trigger.interval.total_seconds() == 30 * 60
        assert list(job.args) == [False]

    async def test_the_addition_is_logged(self, paused, app_log):
        core_scheduler.add_scheduler_job(print, "interval", 60, [], "logged job")

        messages = {r.getMessage() for r in app_log.records if r.name.endswith("core.scheduler")}
        assert messages == {"Added a scheduler job"}

    async def test_a_bad_trigger_raises_and_logs_nothing(self, paused, app_log):
        with pytest.raises(LookupError):
            core_scheduler.add_scheduler_job(print, "no-such-trigger", 60, [], "bad trigger job")

        assert [r for r in app_log.records if r.name.endswith("core.scheduler")] == []
        assert paused.get_jobs() == []


class TestStopScheduler:
    async def test_a_running_scheduler_is_shut_down(self, paused):
        core_scheduler.stop_scheduler()
        turned = asyncio.Event()
        asyncio.get_running_loop().call_soon(turned.set)
        await turned.wait()

        assert not paused.running

    async def test_stopping_one_that_is_not_running_is_harmless(self, scheduler):
        core_scheduler.stop_scheduler()

        assert not scheduler.running


class TestRunLockedJob:
    def test_the_job_runs_when_the_lock_is_free(self):
        operation = Recorder("done")

        assert core_scheduler.run_locked_job("provider_sync", operation, 1) == "done"
        assert operation.calls == [(1,)]

    def test_the_job_is_skipped_while_another_replica_holds_the_lock(self):
        operation = Recorder()

        with _held_by_another_replica("provider_sync"):
            assert core_scheduler.run_locked_job("provider_sync", operation, 1) is None

        assert operation.calls == []

    def test_the_lock_is_released_when_the_job_ends(self):
        core_scheduler.run_locked_job("provider_sync", Recorder())

        with _platform().lock.try_acquire("provider_sync") as acquired:
            assert acquired


class TestRunOnce:
    async def test_a_one_shot_job_is_queued_under_its_id_and_a_repeat_coalesces(self, paused):
        core_scheduler.run_once(print, job_id="job", description="job")
        core_scheduler.run_once(print, job_id="job", description="job")

        assert [job.id for job in paused.get_jobs()] == ["job"]

    async def test_with_a_lock_the_job_runs_only_under_that_lock(self, paused):
        operation = Recorder()
        core_scheduler.run_once(operation, job_id="job", description="job", lock_name="lock")
        job = paused.get_job("job")

        with _held_by_another_replica("lock"):
            job.func(*job.args)
        assert operation.calls == []

        job.func(*job.args)
        assert operation.calls == [()]


class TestRunDueJob:
    """Every replica fires its own interval; a locked job still runs once per interval across them."""

    def test_a_second_replica_inside_the_interval_skips(self):
        operation = Recorder("ran")

        assert core_scheduler.run_due_job("sweep", 5, operation, 1) == "ran"
        assert core_scheduler.run_due_job("sweep", 5, operation, 1) is None
        assert operation.calls == [(1,)]

    def test_each_job_has_its_own_interval(self):
        operation = Recorder()

        core_scheduler.run_due_job("sweep", 5, operation)
        core_scheduler.run_due_job("purge", 5, operation)

        assert len(operation.calls) == 2

    def test_the_mark_expires_before_this_replicas_next_tick(self, clock):
        """Counted from the start of the run, so the replica that ran is never blocked from its own next run."""
        interval_minutes = 5

        def slow_run():
            clock(120)

        core_scheduler.run_due_job("sweep", interval_minutes, slow_run)
        mark_ttl = int(interval_minutes * 60 * 0.9) - 120

        clock(mark_ttl - 1)
        assert _mark("sweep") is not None
        clock(2)
        assert _mark("sweep") is None

    def test_a_run_that_took_its_whole_interval_leaves_no_mark(self, clock):
        core_scheduler.run_due_job("sweep", 5, lambda: clock(300))

        assert _mark("sweep") is None

    def test_a_failed_run_is_retried_at_the_next_tick(self):
        """A failure marks nothing, so the next tick of any replica runs the job again."""
        operation = Recorder(RuntimeError("boom"), "ran")

        with pytest.raises(RuntimeError):
            core_scheduler.run_due_job("sweep", 1440, operation)
        assert core_scheduler.run_due_job("sweep", 1440, operation) == "ran"
        assert core_scheduler.run_due_job("sweep", 1440, operation) is None
        assert len(operation.calls) == 2

    def test_a_run_marks_nothing_until_it_finishes(self):
        """A replica that dies mid-run leaves no mark behind, so the next tick of another replica runs the job."""
        marks_seen_while_running = []

        def operation():
            marks_seen_while_running.append(_mark("sweep"))

        core_scheduler.run_due_job("sweep", 1440, operation)

        assert marks_seen_while_running == [None]
        assert _mark("sweep") is not None

    def test_an_unreachable_state_store_still_runs_the_job_under_its_lock(self, monkeypatch):
        def down(*args, **kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(_platform().state, "get", down)
        monkeypatch.setattr(_platform().state, "set", down)
        operation = Recorder()

        core_scheduler.run_due_job("sweep", 5, operation)

        assert operation.calls == [()]

    def test_another_replica_holding_the_lock_skips_without_marking(self):
        operation = Recorder()

        with _held_by_another_replica("sweep"):
            assert core_scheduler.run_due_job("sweep", 5, operation) is None

        assert operation.calls == []
        assert _mark("sweep") is None

    async def test_an_async_job_is_due_once_per_interval_too(self):
        operation = AsyncRecorder("ran")

        assert await core_scheduler._run_due_async_job("sync", 5, operation.run) == "ran"
        assert await core_scheduler._run_due_async_job("sync", 5, operation.run) is None
        assert len(operation.calls) == 1

    async def test_a_failed_async_run_is_retried_at_the_next_tick(self):
        operation = AsyncRecorder(RuntimeError("boom"), "ran")

        with pytest.raises(RuntimeError):
            await core_scheduler._run_due_async_job("sync", 1440, operation.run)
        assert await core_scheduler._run_due_async_job("sync", 1440, operation.run) == "ran"
        assert len(operation.calls) == 2

    async def test_an_async_job_is_skipped_while_another_replica_holds_the_lock(self):
        operation = AsyncRecorder()

        with _held_by_another_replica("sync"):
            assert await core_scheduler._run_due_async_job("sync", 5, operation.run) is None

        assert operation.calls == []


class TestDatabaseOutage:
    """A database out of reach is a degraded dependency: the run is skipped with a warning and the next tick runs it."""

    def test_a_lock_the_database_cannot_take_skips_the_run_with_a_warning(self, database_down, app_log):
        operation = Recorder()

        assert core_scheduler.run_due_job("sweep", 5, operation) is None

        assert operation.calls == []
        _assert_one_outage_warning(app_log, "sweep")

    def test_a_connection_lost_during_the_run_skips_it_and_the_next_tick_runs_it(self, app_log):
        operation = Recorder(test_database.lost_connection_error(), "ran")

        assert core_scheduler.run_due_job("sweep", 5, operation) is None
        assert _mark("sweep") is None
        _assert_one_outage_warning(app_log, "sweep")
        assert core_scheduler.run_due_job("sweep", 5, operation) == "ran"

    @pytest.mark.parametrize(
        "error",
        [
            IntegrityError("INSERT", {}, psycopg.errors.UniqueViolation("duplicate key")),
            # A job that times out on a lock or a statement points at a slow query, not at an outage.
            OperationalError("UPDATE", {}, psycopg.errors.LockNotAvailable("lock timeout")),
            OperationalError("SELECT", {}, psycopg.errors.QueryCanceled("statement timeout")),
        ],
        ids=["integrity", "lock-timeout", "statement-timeout"],
    )
    def test_any_other_database_error_reaches_the_scheduler(self, error):
        with pytest.raises(type(error)):
            core_scheduler.run_due_job("sweep", 5, Recorder(error))

    async def test_an_async_job_is_skipped_too(self, database_down, app_log):
        operation = AsyncRecorder()

        assert await core_scheduler._run_due_async_job("sync", 5, operation.run) is None

        assert operation.calls == []
        _assert_one_outage_warning(app_log, "sync")

    async def test_a_job_without_a_lock_is_skipped_and_runs_at_the_next_tick(self, paused, app_log):
        operation = Recorder(test_database.lost_connection_error(), "ran")
        core_scheduler.start_scheduler([core_scheduler.ScheduledJob(operation, 5, "unlocked")])
        job = paused.get_job("endurain_unlocked")

        assert job.func(*job.args) is None
        assert job.func(*job.args) == "ran"
        _assert_one_unlocked_outage_warning(app_log, "unlocked")

    async def test_an_async_job_without_a_lock_is_skipped_too(self, paused, app_log):
        operation = AsyncRecorder(test_database.lost_connection_error(), "ran")
        core_scheduler.start_scheduler([core_scheduler.ScheduledJob(operation.run, 5, "unlocked")])
        job = paused.get_job("endurain_unlocked")

        assert await job.func(*job.args) is None
        assert await job.func(*job.args) == "ran"
        _assert_one_unlocked_outage_warning(app_log, "unlocked")

    async def test_a_one_shot_job_without_a_lock_is_skipped_too(self, paused, app_log):
        operation = Recorder(test_database.lost_connection_error())
        core_scheduler.run_once(operation, job_id="job", description="audit trail maintenance")
        job = paused.get_job("job")

        assert job.func(*job.args) is None
        _assert_one_unlocked_outage_warning(app_log, "audit trail maintenance")

    def test_a_one_shot_locked_job_is_skipped_too(self, database_down, app_log):
        operation = Recorder()

        assert core_scheduler.run_locked_job("provider_sync", operation) is None

        assert operation.calls == []
        _assert_one_outage_warning(app_log, "provider_sync")


@pytest.fixture
def database_down():
    """Coordinate through advisory locks on a database that refuses every connection."""
    engine = test_database.unreachable_engine()
    platform_runtime.set_active_platform(dataclasses.replace(_platform(), lock=PgAdvisoryLock(engine)))
    yield
    engine.dispose()


def _assert_one_unlocked_outage_warning(app_log, description: str) -> None:
    [record] = [record for record in app_log.records if record.levelno >= logging.WARNING]
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert (record.job, record.error) == (description, "OperationalError")


def _assert_one_outage_warning(app_log, lock_name: str) -> None:
    [record] = app_log.records
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert (record.lock_name, record.error) == (lock_name, "OperationalError")
