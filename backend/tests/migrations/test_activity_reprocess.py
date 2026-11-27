"""The reprocess data migration: the job that walks the old activities, and how it is requested and run."""

import contextlib
import dataclasses
import uuid
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock

import jasil.jobs.registry as jobs_registry
import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
import pytest
import sqlalchemy as sa
from jasil.events import new_event
from jasil.jobs import ContinueJob
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.job_queues as core_job_queues
import core.local_pool as core_local_pool
import migrations.activity_reprocess as reprocess_job
import migrations.events as migrations_events
import migrations.models as migrations_models
import modules.activities.activity.models as activity_models
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_ingestion.migration_service as ingestion_migration
import modules.activities.activity_laps.models as lap_models
import modules.activities.computation as activities_computation
from tests._factories.activities import make_activity
from tests._factories.reprocess import BOGUS_DERIVED, OLD, RUN, STRENGTH, degrade, import_fixture
from tests._factories.users import make_user

_CURRENT = activities_computation.ANALYSIS_VERSION


@pytest.fixture
def storage():
    return platform_runtime.get_active_platform().storage


def _row(db: Session, activity_id: uuid.UUID) -> activity_models.Activity:
    db.expire_all()
    return db.execute(
        sa.select(activity_models.Activity).where(activity_models.Activity.id == activity_id)
    ).scalar_one()


def _executed(db: Session) -> bool:
    db.expire_all()
    return db.get(migrations_models.Migration, reprocess_job.MIGRATION_ID).executed


def _snapshot(db: Session, activity_ids: list[uuid.UUID]) -> list[tuple]:
    """Every column of the activities, and how many laps each has, so two runs compare by content."""
    db.expire_all()
    rows = []
    for activity_id in activity_ids:
        row = db.get(activity_models.Activity, activity_id)
        values = tuple((column.key, getattr(row, column.key)) for column in activity_models.Activity.__table__.columns)
        laps = db.scalar(
            sa.select(sa.func.count())
            .select_from(lap_models.ActivityLaps)
            .where(lap_models.ActivityLaps.activity_id == activity_id)
        )
        rows.append((values, laps))
    return rows


def _values(db: Session, activity_ids: list[uuid.UUID]) -> list[tuple]:
    """Every column of the activities but the analysis version."""
    db.expire_all()
    return [
        tuple(
            (column.key, getattr(db.get(activity_models.Activity, activity_id), column.key))
            for column in activity_models.Activity.__table__.columns
            if column.key != "analysis_version"
        )
        for activity_id in activity_ids
    ]


def _old_activities(db: Session, tmp_path: Path, storage, *, users: int = 2) -> list[uuid.UUID]:
    """Import a run and a strength session for each of several users, then make each look like an old analysis."""
    ids: list[uuid.UUID] = []
    for _ in range(users):
        user = make_user(db, timezone="Europe/Lisbon")
        db.commit()
        for source in (RUN, STRENGTH):
            [activity_id] = import_fixture(db, user.id, source, tmp_path, storage)
            degrade(db, activity_id)
            ids.append(activity_id)
    return ids


def _reprocessed(db: Session, activity_id: uuid.UUID) -> bool:
    row = _row(db, activity_id)
    return row.analysis_version == _CURRENT and row.distance != BOGUS_DERIVED["distance"]


def _logged(caplog, activity_id: uuid.UUID) -> list:
    return [r for r in caplog.records if str(getattr(r, "activity_id", None)) == str(activity_id)]


class TestRunningABatch:
    def test_reprocesses_every_old_activity_of_several_users_and_marks_the_migration_executed(
        self, db, tmp_path, storage
    ):
        ids = _old_activities(db, tmp_path, storage)
        assert not _executed(db)

        remaining = reprocess_job.run_batch(storage, None)

        assert remaining is False
        assert all(_reprocessed(db, activity_id) for activity_id in ids)
        assert _executed(db)

    def test_walks_more_than_one_listed_batch(self, db, tmp_path, storage, monkeypatch):
        monkeypatch.setattr(reprocess_job, "_BATCH_SIZE", 1)
        ids = _old_activities(db, tmp_path, storage)

        assert reprocess_job.run_batch(storage, None) is False

        assert all(_reprocessed(db, activity_id) for activity_id in ids)

    def test_a_pass_that_spends_its_budget_stops_part_way_and_the_next_one_finishes(self, db, tmp_path, storage):
        ids = _old_activities(db, tmp_path, storage)

        first = reprocess_job.run_batch(storage, 0)

        assert first is True
        assert 0 < sum(_reprocessed(db, activity_id) for activity_id in ids) < len(ids)
        assert not _executed(db)

        results = [reprocess_job.run_batch(storage, 0) for _ in range(len(ids))]

        assert results[-1] is False
        assert all(_reprocessed(db, activity_id) for activity_id in ids)
        assert _executed(db)

    def test_a_second_full_run_changes_nothing(self, db, tmp_path, storage):
        ids = _old_activities(db, tmp_path, storage)
        reprocess_job.run_batch(storage, None)
        after_first = _snapshot(db, ids)

        assert reprocess_job.run_batch(storage, None) is False

        assert _snapshot(db, ids) == after_first
        assert _executed(db)

    def test_an_activity_without_a_file_and_a_strava_activity_are_stamped_and_keep_their_values(
        self, db, tmp_path, storage
    ):
        user = make_user(db)
        manual = make_activity(db, user.id, start_time=OLD)
        strava = make_activity(db, user.id, start_time=OLD.replace(day=2), strava_activity_id=1234)
        db.commit()
        ids = [manual.id, strava.id]
        before = _values(db, ids)

        reprocess_job.run_batch(storage, None)

        assert _values(db, ids) == before
        assert all(_row(db, activity_id).analysis_version == _CURRENT for activity_id in ids)
        assert _executed(db)

    def test_a_corrupted_file_is_stamped_and_logged_and_the_run_goes_on(self, db, tmp_path, storage, caplog):
        broken, healthy = _old_activities(db, tmp_path, storage, users=1)
        file_storage.store_activity_file(broken, ".fit", b"this is not a fit file at all", storage)
        before = _values(db, [broken])

        reprocess_job.run_batch(storage, None)

        assert _row(db, broken).analysis_version == _CURRENT
        assert _values(db, [broken]) == before
        assert _logged(caplog, broken)
        assert _reprocessed(db, healthy)
        assert _executed(db)

    @pytest.mark.parametrize(
        "error",
        [RuntimeError("boom"), IntegrityError("INSERT", {}, Exception("duplicate key"))],
        ids=["a bug", "a regroup parent key taken by a concurrent import"],
    )
    def test_an_exception_in_one_activity_is_isolated_logged_and_the_activity_stamped(
        self, db, tmp_path, storage, monkeypatch, caplog, error
    ):
        bad, *others = sorted(_old_activities(db, tmp_path, storage))
        real = ingestion_migration.reprocess_activity

        def flaky(activity_id, provider):
            if activity_id == bad:
                raise error
            return real(activity_id, provider)

        monkeypatch.setattr(ingestion_migration, "reprocess_activity", flaky)

        assert reprocess_job.run_batch(storage, None) is False

        assert _row(db, bad).analysis_version == _CURRENT
        assert all(_reprocessed(db, activity_id) for activity_id in others)
        [record] = [r for r in _logged(caplog, bad) if r.levelname == "ERROR"]
        assert record.exc_info is not None
        assert _executed(db)

    def test_an_activity_is_stamped_whatever_its_outcome_so_the_walk_always_ends(
        self, db, tmp_path, storage, monkeypatch
    ):
        # A reprocess that reports success without stamping would otherwise be listed again and again.
        activity_id, *_ = sorted(_old_activities(db, tmp_path, storage, users=1))
        monkeypatch.setattr(
            ingestion_migration,
            "reprocess_activity",
            lambda _activity_id, _provider: ingestion_migration.ReprocessOutcome.REPROCESSED,
        )

        reprocess_job.run_batch(storage, 0)

        assert _row(db, activity_id).analysis_version == _CURRENT

    @pytest.mark.parametrize(
        "outage",
        [
            platform_providers.StorageBackendUnavailableError("storage is down"),
            core_exceptions.ServiceUnavailableError("busy"),
            OperationalError("SELECT 1", {}, Exception("connection lost"), connection_invalidated=True),
        ],
        ids=["storage", "service", "database"],
    )
    def test_an_outage_propagates_so_the_attempt_is_retried_and_the_activity_is_not_stamped(
        self, db, tmp_path, storage, monkeypatch, outage
    ):
        ids = _old_activities(db, tmp_path, storage, users=1)

        def down(*_args):
            raise outage

        monkeypatch.setattr(ingestion_migration, "reprocess_activity", down)

        with pytest.raises(type(outage)):
            reprocess_job.run_batch(storage, None)

        assert all(_row(db, activity_id).analysis_version == 0 for activity_id in ids)
        assert not _executed(db)


class _HeldLock:
    """A lock provider whose locks another replica already holds."""

    @contextlib.contextmanager
    def try_acquire(self, name: str, ttl_seconds: int | None = None):
        yield False


class _RecordingLock:
    """A lock provider that grants every lock and remembers the names it was asked for."""

    def __init__(self) -> None:
        self.names: list[str] = []

    @contextlib.contextmanager
    def try_acquire(self, name: str, ttl_seconds: int | None = None):
        self.names.append(name)
        yield True


def _use_lock(lock) -> None:
    platform_runtime.set_active_platform(dataclasses.replace(platform_runtime.get_active_platform(), lock=lock))


class _RecordedPool(core_local_pool.BoundedPool):
    """The reprocess pool, whose jobs a test waits for."""

    def __init__(self) -> None:
        super().__init__("test-reprocess", workers=1, max_pending=1)
        self.futures: list[Future] = []

    def submit_waiting(self, wait_seconds, run, /, *args, **kwargs):
        future = super().submit_waiting(wait_seconds, run, *args, **kwargs)
        self.futures.append(future)
        return future

    def drain(self) -> None:
        for future in self.futures:
            future.exception(timeout=60)


@pytest.fixture
def durable_jobs(monkeypatch) -> None:
    """Run the test on the durable profile: the request is staged in the outbox for a worker."""
    monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
    settings = jasil_settings.get_settings()
    jasil_settings.configure(dataclasses.replace(settings, jobs=dataclasses.replace(settings.jobs, enabled=True)))
    reprocess_job.register_durable_handlers(jobs_registry.registry)


@pytest.fixture
def pool(monkeypatch):
    recorded = _RecordedPool()
    monkeypatch.setattr(reprocess_job, "_pool", recorded)
    yield recorded
    recorded.shutdown(wait=True)


def _requests(db: Session) -> list[str]:
    return list(
        db.scalars(
            sa.text("SELECT event_id FROM jasil_event_outbox WHERE event_type = :t ORDER BY created_at"),
            {"t": migrations_events.ACTIVITY_REPROCESS_REQUESTED},
        )
    )


class TestRequestingTheReprocessAtStartup:
    def test_with_durable_jobs_the_requests_of_one_hour_queue_one_pass_and_the_next_hour_another(
        self, db, durable_jobs
    ):
        clock = platform_runtime.get_active_platform().clock
        hour = f"{clock.now():%Y%m%d%H}"

        reprocess_job.request_reprocess()
        reprocess_job.request_reprocess()

        assert _requests(db) == [f"activity-reprocess-v{_CURRENT}-{hour}"]

        clock.advance(3600)
        reprocess_job.request_reprocess()

        assert len(_requests(db)) == 2

    def test_with_durable_jobs_it_runs_nothing_itself(self, db, tmp_path, storage, durable_jobs):
        ids = _old_activities(db, tmp_path, storage, users=1)

        reprocess_job.request_reprocess()

        assert all(_row(db, activity_id).analysis_version == 0 for activity_id in ids)
        assert not _executed(db)

    def test_without_durable_jobs_the_run_goes_to_the_pool_and_publishes_nothing(
        self, committed_sessions, tmp_path, storage, pool, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", False)
        with committed_sessions() as db:
            ids = _old_activities(db, tmp_path, storage, users=1)

        reprocess_job.request_reprocess()
        pool.drain()

        with committed_sessions() as db:
            assert all(_reprocessed(db, activity_id) for activity_id in ids)
            assert _executed(db)
            assert _requests(db) == []

    def test_a_request_while_a_run_is_queued_does_not_queue_another(self, db, storage, pool, monkeypatch):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", False)
        submitted: list[object] = []
        monkeypatch.setattr(pool, "submit", lambda *args, **kwargs: submitted.append(args) or Future())
        reprocess_job.request_reprocess()
        monkeypatch.setattr(
            pool, "submit", lambda *args, **kwargs: (_ for _ in ()).throw(core_local_pool.PoolFullError("full"))
        )

        reprocess_job.request_reprocess()

        assert len(submitted) == 1

    @pytest.mark.parametrize("durable", [True, False])
    def test_once_the_migration_is_executed_it_does_nothing(self, db, pool, monkeypatch, durable):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", durable)
        db.get(migrations_models.Migration, reprocess_job.MIGRATION_ID).executed = True
        db.commit()
        submitted: list[object] = []
        monkeypatch.setattr(pool, "submit", lambda *args, **kwargs: submitted.append(args))

        reprocess_job.request_reprocess()

        assert submitted == []
        assert _requests(db) == []


def _event():
    return new_event(migrations_events.ACTIVITY_REPROCESS_REQUESTED, {}, source="test")


@pytest.fixture
def one_activity_per_pass(monkeypatch):
    """A durable pass budget of nothing, so a pass settles one activity."""
    monkeypatch.setattr(core_config.settings, "JOBS_LEASE_SECONDS", 0)
    monkeypatch.setattr(core_job_queues, "PASS_MIN_SECONDS", 0)


class TestTheDurableHandler:
    def test_a_pass_with_work_left_continues_the_same_job_until_the_last_one_ends_it(
        self, db, tmp_path, storage, one_activity_per_pass
    ):
        ids = _old_activities(db, tmp_path, storage, users=1)

        with pytest.raises(ContinueJob) as continued:
            reprocess_job.handle_reprocess_requested(_event())

        assert continued.value.delay_seconds == 0
        assert not _executed(db)
        for _ in range(len(ids)):
            with contextlib.suppress(ContinueJob):
                reprocess_job.handle_reprocess_requested(_event())
        assert all(_reprocessed(db, activity_id) for activity_id in ids)
        assert _executed(db)

    def test_a_pass_that_finishes_everything_ends_without_continuing(self, db, tmp_path, storage):
        ids = _old_activities(db, tmp_path, storage, users=1)

        reprocess_job.handle_reprocess_requested(_event())

        assert all(_reprocessed(db, activity_id) for activity_id in ids)
        assert _executed(db)

    def test_is_registered_on_the_background_queue_with_an_exempt_net(self):
        registry = jobs_registry.JobHandlerRegistry()

        reprocess_job.register_durable_handlers(registry)

        assert registry.subscribers_for(migrations_events.ACTIVITY_REPROCESS_REQUESTED) == (
            reprocess_job.REPROCESS_SUBSCRIBER_ID,
        )
        assert registry.queue_for(reprocess_job.REPROCESS_SUBSCRIBER_ID) == core_job_queues.BACKGROUND
        [net] = reprocess_job.DURABLE_SUBSCRIBER_NETS
        assert (net.subscriber_id, net.backfill) == (reprocess_job.REPROCESS_SUBSCRIBER_ID, None)
        assert net.exempt_reason


class TestTwoPassesNeverRunAtOnce:
    def test_a_pass_takes_the_migration_lock(self, db, storage):
        lock = _RecordingLock()
        _use_lock(lock)

        reprocess_job.handle_reprocess_requested(_event())

        assert lock.names == [reprocess_job.LOCK_NAME]

    def test_a_durable_pass_does_nothing_while_another_pass_holds_the_lock(self, db, tmp_path, storage):
        ids = _old_activities(db, tmp_path, storage, users=1)
        _use_lock(_HeldLock())

        reprocess_job.handle_reprocess_requested(_event())

        assert all(_row(db, activity_id).analysis_version == 0 for activity_id in ids)
        assert not _executed(db)

    def test_a_pool_run_takes_the_same_lock_and_does_nothing_while_it_is_held(
        self, db, tmp_path, storage, pool, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", False)
        ids = _old_activities(db, tmp_path, storage, users=1)
        _use_lock(_HeldLock())

        reprocess_job.request_reprocess()
        pool.drain()

        assert all(_row(db, activity_id).analysis_version == 0 for activity_id in ids)
        assert not _executed(db)


class TestShutdown:
    def test_stops_the_pool(self, monkeypatch):
        stub = MagicMock()
        monkeypatch.setattr(reprocess_job, "_pool", stub)

        reprocess_job.shutdown_pool()

        stub.shutdown.assert_called_once_with()
