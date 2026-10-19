"""Concurrent writers of ingestion jobs, activity locations and the shared locks.

Each of these is a race between processes (API replicas, workers, the stale-job
reaper) that a mocked session or a single SQLite connection cannot reproduce:
they need separate connections, real row locks and a database-enforced unique
index.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jasil.backends.lock_pg import PgAdvisoryLock
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_thumbnail.service as thumbnail_service
from tests._helpers.db import ensure_user

_USER_ID = 1
_LEASE = timedelta(seconds=300)
_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, _USER_ID)
    return pg_factory


def _add_job(factory, kind=ingestion_constants.IngestionJobKind.UPLOAD, *, idle_hours: int = 0, **extra) -> str:
    job_id = str(uuid.uuid4())
    with factory() as db:
        ingestion_crud.create_ingestion_job(job_id, _USER_ID, kind, db, filename="ride.gpx", staged_key=job_id, **extra)
        db.commit()
    if idle_hours:
        with factory() as db:
            db.execute(
                text(
                    "UPDATE activity_ingestion_jobs SET updated_at = now() - make_interval(hours => :h) WHERE id = :i"
                ),
                {"h": idle_hours, "i": job_id},
            )
            db.commit()
    return job_id


def _state(factory, job_id: str) -> tuple[str, str | None]:
    """Read a job through a fresh session: ``(status, error_code)``."""
    with factory() as db:
        row = db.get(ingestion_models.ActivityIngestionJob, job_id)
        db.refresh(row)
        return row.status, row.error_code


class TestTerminalJobsAreFinal:
    def test_a_late_failure_does_not_overwrite_a_completed_job(self, factory):
        """A worker that lost its lease finishing after the replacement worker did."""
        job_id = _add_job(factory)
        with factory() as db:
            ingestion_crud.mark_completed(job_id, [1], db)
            db.commit()

        with factory() as db:
            ingestion_crud.mark_failed(job_id, ingestion_constants.IngestionJobErrorCode.NO_ACTIVITIES_FOUND, db)
            db.commit()

        assert _state(factory, job_id) == ("completed", None)

    def test_two_writers_of_one_job_serialize_on_the_row_lock(self, factory):
        job_id = _add_job(factory)
        first = factory()
        ingestion_crud.mark_completed(job_id, [1], first)  # holds the row lock, uncommitted
        second_done = threading.Event()

        def second_writer() -> None:
            with factory() as db:
                ingestion_crud.mark_failed(job_id, ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED, db)
                db.commit()
            second_done.set()

        thread = threading.Thread(target=second_writer)
        thread.start()
        try:
            assert not second_done.wait(0.7), "the second writer must wait for the first"
        finally:
            first.commit()
            first.close()
            thread.join(timeout=10)

        assert second_done.is_set()
        assert _state(factory, job_id) == ("completed", None)


class TestStaleJobReaper:
    def test_it_fails_idle_jobs_and_returns_their_staged_keys(self, factory):
        idle = _add_job(factory, idle_hours=48)
        with factory() as db:
            failed = ingestion_crud.fail_jobs_idle_since(
                datetime.now(UTC) - timedelta(hours=24), ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED, db
            )
            db.commit()

        assert failed == [(idle, idle)]
        assert _state(factory, idle) == ("failed", "processing_failed")

    def test_it_skips_a_row_a_worker_is_writing_without_blocking(self, factory):
        busy = _add_job(factory, idle_hours=48)
        idle = _add_job(factory, idle_hours=48)
        worker = factory()
        ingestion_crud.mark_completed(busy, [2], worker)  # the worker's uncommitted outcome
        result: dict = {}

        def reap() -> None:
            with factory() as db:
                result["failed"] = ingestion_crud.fail_jobs_idle_since(
                    datetime.now(UTC) - timedelta(hours=24),
                    ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                    db,
                )
                db.commit()

        thread = threading.Thread(target=reap)
        thread.start()
        try:
            thread.join(timeout=5)
            assert not thread.is_alive(), "the reaper must not wait on a locked row"
        finally:
            # Release the row even when the assertion fails, or the blocked reaper
            # (and the schema teardown behind it) would hang the run.
            worker.commit()
            worker.close()
            thread.join(timeout=10)

        assert {job_id for job_id, _key in result["failed"]} == {idle}
        assert _state(factory, busy) == ("completed", None)
        assert _state(factory, idle)[0] == "failed"


class TestClaiming:
    def test_exactly_one_of_many_concurrent_claimers_owns_the_job(self, factory):
        job_id = _add_job(factory)
        barrier = threading.Barrier(6)
        outcomes: list[bool] = []

        def claim() -> None:
            barrier.wait()
            with factory() as db:
                outcomes.append(ingestion_crud.mark_processing(job_id, db, lease=_LEASE))
                db.commit()

        threads = [threading.Thread(target=claim) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert outcomes.count(True) == 1
        assert _state(factory, job_id)[0] == "processing"

    def test_a_claim_expires_against_the_database_clock_not_the_callers(self, factory):
        """The lease age is read from the row's own timestamps, so a replica's clock cannot revive a claim."""
        job_id = _add_job(factory)
        with factory() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
            db.commit()
        with factory() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is False

        with factory() as db:
            db.execute(
                text("UPDATE activity_ingestion_jobs SET updated_at = now() - interval '10 minutes' WHERE id = :id"),
                {"id": job_id},
            )
            db.commit()
        with factory() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
            db.commit()
        with factory() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is False

    def test_a_second_active_bulk_import_for_one_user_is_refused_by_the_database(self, factory):
        kind = ingestion_constants.IngestionJobKind.BULK_IMPORT
        _add_job(factory, kind, import_source="strava", files_total=1)

        with pytest.raises(IntegrityError):
            _add_job(factory, kind, import_source="strava", files_total=1)


def _add_activity_without_location(factory) -> int:
    core = activity_contracts.ActivityCore(
        user_id=_USER_ID,
        name="Ride",
        distance=1000,
        activity_type=1,
        start_time="2026-07-28T09:00:00",
        end_time="2026-07-28T10:00:00",
        total_elapsed_time=3600.0,
        total_timer_time=3540.0,
        **{flag: False for flag in _PRIVACY_FLAGS},
    )
    with factory() as db:
        created = activity_crud.create_activity(core, db)
        db.commit()
        return created.id


def test_the_first_location_write_wins_and_a_later_one_does_not_overwrite_it(factory):
    """Two replicas geocoding the same activity, or a user editing it in between."""
    activity_id = _add_activity_without_location(factory)

    with factory() as first, factory() as second:
        wrote_first = activity_crud.update_activity_location(activity_id, "Lisbon", None, "Portugal", first)
        first.commit()
        wrote_second = activity_crud.update_activity_location(activity_id, "Porto", None, "Portugal", second)
        second.commit()

    with factory() as db:
        city = db.scalar(select(activity_models.Activity.city).where(activity_models.Activity.id == activity_id))
    assert (wrote_first, wrote_second, city) == (True, False, "Lisbon")


class TestRegenerationLock:
    @pytest.fixture
    def lock(self, factory):
        return PgAdvisoryLock(factory.kw["bind"])

    @staticmethod
    def _hold(lock, name: str) -> tuple[threading.Event, threading.Thread]:
        """Hold ``name`` on its own connection until the returned event is set."""
        held, release = threading.Event(), threading.Event()

        def holder() -> None:
            with lock.try_acquire(name):
                held.set()
                release.wait(20)

        thread = threading.Thread(target=holder)
        thread.start()
        assert held.wait(5)
        return release, thread

    def test_regeneration_refuses_while_another_holder_has_the_backfill_lock(
        self, factory, lock, _publish_local_platform
    ):
        platform = _publish_local_platform
        release, thread = self._hold(lock, "thumbnail_backfill")
        try:
            with factory() as db, pytest.raises(core_exceptions.ConflictError):
                thumbnail_service.delete_and_regenerate_all_activity_thumbnails(
                    platform.storage, lock, platform.clock, db
                )
        finally:
            release.set()
            thread.join(timeout=10)

    def test_regeneration_runs_once_the_lock_is_free(self, factory, lock, _publish_local_platform):
        platform = _publish_local_platform
        with factory() as db:
            thumbnail_service.delete_and_regenerate_all_activity_thumbnails(platform.storage, lock, platform.clock, db)

    def test_the_backfill_pass_skips_quietly_while_the_lock_is_held(self, factory, lock, _publish_local_platform):
        platform = _publish_local_platform
        release, thread = self._hold(lock, "thumbnail_backfill")
        try:
            with factory() as db:
                thumbnail_service.generate_missing_activity_thumbnails(platform.storage, lock, platform.clock, db)
        finally:
            release.set()
            thread.join(timeout=10)
