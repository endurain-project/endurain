"""Deferred refreshes are released by ``SELECT ... FOR UPDATE SKIP LOCKED`` against real PostgreSQL.

Every replica's scheduler releases the refreshes whose rate limit has cleared. Two of them running together must not
release a job twice (or wait on each other), the due test reads the database clock, and a released job is claimed
once like any other and recovered through the lease when its claimer dies.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from tests._factories.users import make_user

import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud

_LEASE = timedelta(seconds=300)


def _user(factory) -> uuid.UUID:
    with factory() as db:
        user_id = make_user(db).id
        db.commit()
    return user_id


def _deferred_job(factory, user_id: uuid.UUID, *, due_in: timedelta) -> uuid.UUID:
    """Store a refresh that a provider's rate limit deferred until ``due_in`` from now (negative: already due)."""
    job_id = uuid.uuid4()
    with factory() as db:
        ingestion_crud.create_ingestion_job(
            job_id, user_id, ingestion_constants.IngestionJobKind.REFRESH, db, provider="strava"
        )
        db.commit()
    with factory() as db:
        assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
        ingestion_crud.mark_deferred(job_id, datetime.now(UTC) + due_in, db)
        db.commit()
    return job_id


def _status(factory, job_id: uuid.UUID) -> str:
    with factory() as db:
        return db.execute(text("SELECT status FROM activity_ingestion_jobs WHERE id = :i"), {"i": job_id}).scalar_one()


class TestReleaseDueDeferredJobs:
    def test_only_the_refreshes_whose_wait_is_over_are_released_oldest_wait_first(self, committed_sessions):
        user_id = _user(committed_sessions)
        later = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))
        earlier = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-10))
        waiting = _deferred_job(committed_sessions, user_id, due_in=timedelta(hours=1))

        with committed_sessions() as db:
            released = ingestion_crud.release_due_deferred_jobs(10, db)
            db.commit()

        assert released == [(earlier, user_id), (later, user_id)]
        assert [_status(committed_sessions, job) for job in (earlier, later, waiting)] == [
            "pending",
            "pending",
            "deferred",
        ]
        with committed_sessions() as db:
            retry_after = db.execute(
                text("SELECT retry_after FROM activity_ingestion_jobs WHERE id = :i"), {"i": earlier}
            ).scalar_one()
        assert retry_after is None

    def test_a_call_releases_no_more_than_its_limit(self, committed_sessions):
        user_id = _user(committed_sessions)
        for _ in range(5):
            _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))

        with committed_sessions() as db:
            assert len(ingestion_crud.release_due_deferred_jobs(2, db)) == 2
            db.commit()

        with committed_sessions() as db:
            assert len(ingestion_crud.release_due_deferred_jobs(10, db)) == 3

    def test_a_job_another_replica_is_releasing_is_skipped_without_waiting(self, committed_sessions):
        user_id = _user(committed_sessions)
        held = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-5))
        free = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))

        with committed_sessions() as releasing, committed_sessions() as other:
            assert ingestion_crud.release_due_deferred_jobs(1, releasing) == [(held, user_id)]
            other.execute(text("SET lock_timeout = '2s'"))
            assert ingestion_crud.release_due_deferred_jobs(10, other) == [(free, user_id)]
            other.commit()
            releasing.commit()

    def test_replicas_releasing_together_release_every_job_exactly_once(self, committed_sessions):
        user_id = _user(committed_sessions)
        jobs = {_deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1)) for _ in range(12)}
        barrier = threading.Barrier(4)
        released: list[list[uuid.UUID]] = []
        errors: list[Exception] = []

        def release() -> None:
            try:
                with committed_sessions() as db:
                    barrier.wait()
                    released.append([job_id for job_id, _owner in ingestion_crud.release_due_deferred_jobs(3, db)])
                    db.commit()
            except Exception as err:
                errors.append(err)

        threads = [threading.Thread(target=release) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        everything = [job_id for batch in released for job_id in batch]
        assert errors == []
        assert len(everything) == len(set(everything)) == 12
        assert set(everything) == jobs

    def test_the_wait_is_judged_by_the_database_clock(self, committed_sessions):
        user_id = _user(committed_sessions)
        job_id = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=30))
        with committed_sessions() as db:
            assert ingestion_crud.release_due_deferred_jobs(10, db) == []

        with committed_sessions() as db:
            db.execute(
                text("UPDATE activity_ingestion_jobs SET retry_after = now() - interval '1 second' WHERE id = :i"),
                {"i": job_id},
            )
            db.commit()

        with committed_sessions() as db:
            assert ingestion_crud.release_due_deferred_jobs(10, db) == [(job_id, user_id)]


class TestClaimingAReleasedJob:
    def test_workers_racing_for_a_released_job_claim_it_once(self, committed_sessions):
        user_id = _user(committed_sessions)
        job_id = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))
        with committed_sessions() as db:
            ingestion_crud.release_due_deferred_jobs(10, db)
            db.commit()
        barrier = threading.Barrier(6)
        claims: list[bool] = []

        def claim() -> None:
            with committed_sessions() as db:
                barrier.wait()
                claims.append(ingestion_crud.mark_processing(job_id, db, lease=_LEASE))
                db.commit()

        threads = [threading.Thread(target=claim) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert claims.count(True) == 1
        assert _status(committed_sessions, job_id) == "processing"

    def test_a_claim_whose_worker_died_is_recovered_once_its_lease_has_run_out(self, committed_sessions):
        user_id = _user(committed_sessions)
        job_id = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))
        with committed_sessions() as db:
            ingestion_crud.release_due_deferred_jobs(10, db)
            db.commit()
        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
            db.commit()
        # The worker is gone: nothing touches the row again.
        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is False

        with committed_sessions() as db:
            db.execute(
                text("UPDATE activity_ingestion_jobs SET updated_at = now() - interval '301 seconds' WHERE id = :i"),
                {"i": job_id},
            )
            db.commit()

        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
            db.commit()
        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is False

    def test_a_claim_just_inside_its_lease_is_not_taken_over(self, committed_sessions):
        user_id = _user(committed_sessions)
        job_id = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))
        with committed_sessions() as db:
            ingestion_crud.release_due_deferred_jobs(10, db)
            ingestion_crud.mark_processing(job_id, db, lease=_LEASE)
            db.commit()
        with committed_sessions() as db:
            db.execute(
                text("UPDATE activity_ingestion_jobs SET updated_at = now() - interval '290 seconds' WHERE id = :i"),
                {"i": job_id},
            )
            db.commit()

        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is False

    def test_a_released_claim_is_claimable_at_once_and_a_finished_job_never(self, committed_sessions):
        user_id = _user(committed_sessions)
        job_id = _deferred_job(committed_sessions, user_id, due_in=timedelta(minutes=-1))
        with committed_sessions() as db:
            ingestion_crud.release_due_deferred_jobs(10, db)
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
            ingestion_crud.release_job(job_id, db)
            db.commit()
        assert _status(committed_sessions, job_id) == "pending"

        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is True
            ingestion_crud.mark_completed(job_id, [uuid.uuid4()], db)
            db.commit()
        with committed_sessions() as db:
            db.execute(
                text("UPDATE activity_ingestion_jobs SET updated_at = now() - interval '1 day' WHERE id = :i"),
                {"i": job_id},
            )
            db.commit()

        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job_id, db, lease=_LEASE) is False
