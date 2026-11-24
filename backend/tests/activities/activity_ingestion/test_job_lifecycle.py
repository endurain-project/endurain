"""What a job row records, and what the periodic and startup passes do with the rows and blobs jobs leave behind.

The rows are read back through new sessions and the blobs from the platform's real local storage, so only what was
committed counts.
"""

import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from jasil.providers import StorageBackendUnavailableError
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.local_pool as core_local_pool
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.bulk_import_service as bulk
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.scheduled_jobs as scheduled_jobs
import modules.activities.activity_ingestion.service as ingestion_service
from tests._factories.garmin import activity_gpx, zip_of
from tests._factories.ingestion import (
    ConnectionProbe,
    activities_of,
    age_stored_objects,
    find_job,
    read_job,
    stage_blob,
    stage_job,
    staged_keys,
)
from tests._factories.profile import FaultyStorage
from tests._factories.users import make_user
from tests._helpers import database as test_database

_Kind = ingestion_constants.IngestionJobKind
_ErrorCode = ingestion_constants.IngestionJobErrorCode
_AREA = ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA
_NOT_A_JOB = cast(uuid.UUID, "not-a-job-id")


def _ago(**delta: float) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


@pytest.fixture
def owner(committed_sessions):
    """A committed user."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        db.commit()
    return user


class TestWhatACreatedJobRecords:
    def test_a_new_job_is_pending_and_read_as_queued_by_its_owner_only(self, db):
        user, stranger = make_user(db), make_user(db)
        job = stage_job(db, user.id, staged_key="a.gpx")

        assert job.status == core_job_status.JobState.QUEUED
        assert ingestion_crud.get_ingestion_job(job.id, user.id, db) is not None
        assert ingestion_crud.get_ingestion_job(job.id, stranger.id, db) is None

    def test_the_work_item_names_the_owner_and_key_the_row_holds(self, db):
        user = make_user(db)
        job = stage_job(db, user.id, staged_key="a.gpx")

        assert ingestion_crud.get_job_work_item(job.id, db) == (user.id, "a.gpx")

    def test_a_consumed_or_unknown_job_has_no_work_item(self, db):
        user = make_user(db)
        done = stage_job(db, user.id, status="completed")

        assert ingestion_crud.get_job_work_item(done.id, db) is None
        assert ingestion_crud.get_job_work_item(uuid.uuid4(), db) is None

    def test_a_completed_job_lists_the_activities_it_created_and_drops_its_blob_key(self, db):
        user = make_user(db)
        job = stage_job(db, user.id, status="processing", staged_key="a.gpx")
        created = [uuid.uuid4(), uuid.uuid4()]

        ingestion_crud.mark_completed(job.id, created, db)

        read = ingestion_crud.get_ingestion_job(job.id, user.id, db)
        assert read is not None
        assert (read.status, read.activity_ids) == (core_job_status.JobState.SUCCEEDED, created)
        assert read.finished_at is not None
        assert ingestion_crud.get_job_work_item(job.id, db) is None

    def test_a_failed_job_records_only_the_sanitized_code_and_tells_who_to_notify(self, db):
        user = make_user(db)
        job = stage_job(db, user.id, status="processing", staged_key="a.gpx")

        failed = ingestion_crud.mark_failed(job.id, _ErrorCode.INVALID_FILE, db)

        read = ingestion_crud.get_ingestion_job(job.id, user.id, db)
        assert failed == (user.id, _Kind.UPLOAD)
        assert read is not None
        assert (read.status, read.error_code) == (core_job_status.JobState.FAILED, _ErrorCode.INVALID_FILE)

    def test_nobody_is_told_about_a_job_that_is_missing_or_already_terminal(self, db):
        user = make_user(db)
        done = stage_job(db, user.id, status="completed")

        assert ingestion_crud.mark_failed(uuid.uuid4(), _ErrorCode.INVALID_FILE, db) is None
        assert ingestion_crud.mark_failed(done.id, _ErrorCode.INVALID_FILE, db) is None

    def test_a_late_writer_cannot_overwrite_a_finished_job(self, db):
        user = make_user(db)
        job = stage_job(db, user.id, status="processing")
        winner = uuid.uuid4()
        ingestion_crud.mark_completed(job.id, [winner], db)

        ingestion_crud.mark_failed(job.id, _ErrorCode.PROCESSING_FAILED, db)
        ingestion_crud.mark_completed(job.id, [uuid.uuid4()], db)

        read = ingestion_crud.get_ingestion_job(job.id, user.id, db)
        assert read is not None
        assert (read.status, read.activity_ids) == (core_job_status.JobState.SUCCEEDED, [winner])

    def test_transitions_on_a_missing_job_are_no_ops(self, db):
        ingestion_crud.mark_completed(uuid.uuid4(), [uuid.uuid4()], db)

        assert ingestion_crud.mark_failed(uuid.uuid4(), _ErrorCode.INVALID_FILE, db) is None


class TestAskingAboutJobsThatAreNotThere:
    def test_an_unknown_job_has_no_owner_no_bulk_state_and_no_effect_on_a_batch(self, db):
        user = make_user(db)
        upload = stage_job(db, user.id)

        assert ingestion_crud.get_job_owner(upload.id, db) == user.id
        assert ingestion_crud.get_job_owner(uuid.uuid4(), db) is None
        assert ingestion_crud.get_bulk_import_state(upload.id, db) is None, "an upload is not a bulk import"
        assert ingestion_crud.get_bulk_import_state(uuid.uuid4(), db) is None
        ingestion_crud.touch_job(uuid.uuid4(), db)
        ingestion_crud.record_bulk_progress(uuid.uuid4(), "a.gpx", 1, 0, db)
        ingestion_crud.mark_bulk_completed(uuid.uuid4(), "a.gpx", 1, 0, db)

    def test_no_users_and_no_keys_ask_nothing(self, db):
        assert ingestion_crud.get_user_ids_with_active_refresh([], db) == set()
        assert ingestion_crud.get_referenced_staged_keys([], db) == set()

    def test_a_job_another_worker_runs_is_not_run_again_by_a_duplicate_upload_event(
        self, committed_sessions, owner, storage
    ):
        stage_blob(storage, "a.gpx", activity_gpx())
        with committed_sessions() as db:
            running = stage_job(db, owner.id, status="processing", staged_key="a.gpx")
            db.commit()

        ingestion_service.run_upload_job(running.id, storage)

        assert read_job(committed_sessions, running.id).status == "processing"
        assert activities_of(committed_sessions, owner.id) == []
        assert staged_keys(storage) == ["a.gpx"]


class TestClaimingAJob:
    def test_a_pending_job_moves_to_processing_once(self, committed_sessions, owner):
        with committed_sessions() as db:
            job = stage_job(db, owner.id, kind=_Kind.REFRESH)
            db.commit()
        lease = timedelta(minutes=5)

        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job.id, db, lease=lease) is True
            db.commit()
        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(job.id, db, lease=lease) is False

        assert read_job(committed_sessions, job.id).status == "processing"

    def test_an_unknown_job_is_not_runnable(self, db):
        assert ingestion_crud.mark_processing(uuid.uuid4(), db, lease=timedelta(0)) is False

    def test_a_job_that_finished_is_not_reopened(self, committed_sessions, owner):
        with committed_sessions() as db:
            done = stage_job(db, owner.id, kind=_Kind.REFRESH, status="completed")
            db.commit()

        with committed_sessions() as db:
            assert ingestion_crud.mark_processing(done.id, db, lease=timedelta(0)) is False

        assert read_job(committed_sessions, done.id).status == "completed"

    def test_a_released_attempt_returns_to_pending_for_the_retry(self, committed_sessions, owner):
        with committed_sessions() as db:
            job = stage_job(db, owner.id, kind=_Kind.REFRESH)
            ingestion_crud.mark_processing(job.id, db, lease=timedelta(minutes=5))
            db.commit()

        ingestion_service.release_ingestion_job(job.id)

        assert read_job(committed_sessions, job.id).status == "pending"


class TestFailingAJob:
    def test_records_the_failure_drops_the_blob_and_tells_the_owner(self, committed_sessions, owner, storage, hints):
        stage_blob(storage, "a.gpx", b"x")
        with committed_sessions() as db:
            job = stage_job(db, owner.id, status="processing", staged_key="a.gpx")
            db.commit()

        ingestion_service.fail_ingestion_job(job.id, _ErrorCode.PROCESSING_FAILED, storage)

        row = read_job(committed_sessions, job.id)
        assert (row.status, row.error_code, row.staged_key) == ("failed", "processing_failed", None)
        assert staged_keys(storage) == []
        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]

    def test_a_blob_that_cannot_be_removed_does_not_undo_the_failure(self, committed_sessions, owner, storage):
        stage_blob(storage, "a.gpx", b"x")
        with committed_sessions() as db:
            job = stage_job(db, owner.id, status="processing", staged_key="a.gpx")
            db.commit()
        unreachable = FaultyStorage(storage, faults={"delete": StorageBackendUnavailableError("down")})

        ingestion_service.fail_ingestion_job(job.id, _ErrorCode.PROCESSING_FAILED, unreachable, "a.gpx")

        assert read_job(committed_sessions, job.id).status == "failed"
        assert staged_keys(storage) == ["a.gpx"], "left for the staged blob sweep"

    def test_a_job_that_is_gone_is_a_no_op(self, committed_sessions, storage, hints):
        ingestion_service.fail_ingestion_job(uuid.uuid4(), _ErrorCode.PROCESSING_FAILED, storage)

        assert hints == []


class TestABookkeepingFailureNeverMasksTheFailureBeingHandled:
    """A database error while recording an outcome is logged and left to the retry, never raised over the cause.

    The job id here is not a UUID, so the database layer refuses the statement with a real ``SQLAlchemyError``.
    """

    def test_failing_a_job_logs_the_error_and_keeps_the_blob(self, storage, caplog):
        stage_blob(storage, "a.gpx", b"x")

        with caplog.at_level(logging.ERROR, logger=ingestion_service.logger.name):
            ingestion_service.fail_ingestion_job(
                _NOT_A_JOB,
                _ErrorCode.PROCESSING_FAILED,
                storage,
                "a.gpx",
            )

        assert any("Could not mark an upload job failed" in record.getMessage() for record in caplog.records)
        assert staged_keys(storage) == ["a.gpx"]

    def test_releasing_a_job_logs_the_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger=ingestion_service.logger.name):
            ingestion_service.release_ingestion_job(_NOT_A_JOB)

        assert any("Could not release an ingestion job" in record.getMessage() for record in caplog.records)

    @pytest.fixture
    def database_down(self, monkeypatch):
        """The bookkeeping session opens on a database that refuses every connection, as during an outage."""
        engine = test_database.unreachable_engine()
        monkeypatch.setattr(core_database, "SessionLocal", sessionmaker(bind=engine))
        yield
        engine.dispose()

    def test_releasing_a_job_during_an_outage_is_a_warning(self, database_down, app_log):
        ingestion_service.release_ingestion_job(uuid.uuid4())

        [record] = app_log.records
        assert (record.getMessage(), record.levelno) == (
            "Could not release an ingestion job for retry",
            logging.WARNING,
        )

    def test_failing_a_job_during_an_outage_is_a_warning(self, database_down, app_log, storage):
        ingestion_service.fail_ingestion_job(uuid.uuid4(), _ErrorCode.PROCESSING_FAILED, storage, "a.gpx")

        [record] = app_log.records
        assert (record.getMessage(), record.levelno) == ("Could not mark an upload job failed", logging.WARNING)
        assert (record.exc_info, record.error) == (None, "OperationalError")


class TestErrorCodeFor:
    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (core_exceptions.UnsupportedFormatError("x"), _ErrorCode.UNSUPPORTED_FORMAT),
            (core_exceptions.InvalidInputError("x"), _ErrorCode.INVALID_FILE),
            (core_exceptions.ProcessingError(), _ErrorCode.PROCESSING_FAILED),
        ],
        ids=lambda value: type(value).__name__,
    )
    def test_maps_the_failures_the_owner_can_act_on(self, error, code):
        assert ingestion_service.error_code_for(error) == code

    def test_an_unexpected_failure_does_not_leak_its_message(self):
        code = ingestion_service.error_code_for(RuntimeError("/srv/data/activity_files/secret.fit exploded"))

        assert code == _ErrorCode.PROCESSING_FAILED


class TestRetention:
    def test_prunes_finished_jobs_past_the_window_and_keeps_the_rest(
        self, committed_sessions, owner, platform, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_RETENTION_DAYS", 90)
        with committed_sessions() as db:
            old = stage_job(db, owner.id, status="completed", completed_at=_ago(days=400))
            recent = stage_job(db, owner.id, status="completed", completed_at=_ago(days=5))
            open_job = stage_job(db, owner.id, staged_key="a.gpx")
            db.commit()

        scheduled_jobs.prune_expired_ingestion_jobs()

        assert find_job(committed_sessions, old.id) is None
        assert find_job(committed_sessions, recent.id) is not None
        assert find_job(committed_sessions, open_job.id) is not None

    def test_keeps_everything_when_retention_is_disabled(self, committed_sessions, owner, monkeypatch):
        monkeypatch.setattr(core_config.settings, "JOBS_RETENTION_DAYS", 0)
        with committed_sessions() as db:
            old = stage_job(db, owner.id, status="completed", completed_at=_ago(days=4000))
            db.commit()

        scheduled_jobs.prune_expired_ingestion_jobs()

        assert find_job(committed_sessions, old.id) is not None

    def test_removes_failed_bulk_import_files_past_the_window_only(self, owner, storage, tmp_path, monkeypatch):
        monkeypatch.setattr(core_config.settings, "JOBS_RETENTION_DAYS", 5)
        prefix = ingestion_constants.bulk_import_error_prefix(owner.id)
        storage.save(_AREA, f"{prefix}job/old.gpx", b"old")
        age_stored_objects(tmp_path, 10 * 86400)
        storage.save(_AREA, f"{prefix}job/new.gpx", b"new")

        scheduled_jobs.sweep_stale_bulk_import_errors()

        assert list(storage.list_keys(_AREA, "")) == [f"{prefix}job/new.gpx"]

    @pytest.mark.parametrize("retention_days", [0, -1])
    def test_keeps_failed_bulk_import_files_when_retention_is_disabled(
        self, owner, storage, tmp_path, monkeypatch, retention_days
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_RETENTION_DAYS", retention_days)
        key = f"{ingestion_constants.bulk_import_error_prefix(owner.id)}job/old.gpx"
        storage.save(_AREA, key, b"old")
        age_stored_objects(tmp_path, 3650 * 86400)

        scheduled_jobs.sweep_stale_bulk_import_errors()

        assert list(storage.list_keys(_AREA, "")) == [key]


class TestPassesWithNothingToDo:
    def test_a_prune_a_blob_sweep_and_an_error_sweep_with_nothing_stale_remove_nothing(
        self, committed_sessions, owner, platform, storage, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "JOBS_RETENTION_DAYS", 90)

        ingestion_service.prune_expired_ingestion_jobs(platform.clock)

        assert ingestion_service.sweep_stale_staged_blobs(platform.clock, storage) == 0
        assert ingestion_service.sweep_stale_bulk_import_errors(storage) == 0


class TestTheBackgroundPoolsLifecycle:
    def test_shutting_the_pool_down_waits_for_the_running_job_and_a_later_job_starts_it_again(self, pool):
        ran: list[str] = []

        pool.submit(ran.append, "before")
        ingestion_integration.shutdown_background_ingestion(wait=True)
        pool.submit(ran.append, "after")
        pool.drain()

        assert ran == ["before", "after"]


class TestRunProviderWindow:
    def test_processes_every_activity_and_raises_the_first_failure_after_the_rest(self, owner):
        seen: list[int] = []

        def process(item: int) -> int:
            seen.append(item)
            if item == 2:
                raise ValueError("bad activity")
            return item * 10

        with pytest.raises(ValueError, match="bad activity"):
            ingestion_integration.run_provider_window(
                [1, 2, 3], process, provider="stub", user_id=owner.id, describe=lambda item: {"item": item}
            )

        assert seen == [1, 2, 3]


class TestStaleJobs:
    def test_an_idle_upload_is_failed_and_its_blob_dropped(self, committed_sessions, owner, storage, platform):
        stage_blob(storage, "a.gpx", b"x")
        with committed_sessions() as db:
            job = stage_job(db, owner.id, staged_key="a.gpx", updated_at=_ago(hours=25))
            db.commit()

        scheduled_jobs.fail_stale_ingestion_jobs()

        row = read_job(committed_sessions, job.id)
        assert (row.status, row.error_code, row.staged_key) == ("failed", "processing_failed", None)
        assert staged_keys(storage) == []

    def test_an_idle_job_without_a_blob_is_failed(self, committed_sessions, owner):
        with committed_sessions() as db:
            job = stage_job(db, owner.id, kind=_Kind.REFRESH, status="processing", updated_at=_ago(hours=25))
            db.commit()

        scheduled_jobs.fail_stale_ingestion_jobs()

        assert read_job(committed_sessions, job.id).status == "failed"

    def test_a_job_still_progressing_and_a_finished_job_are_left_alone(self, committed_sessions, owner):
        with committed_sessions() as db:
            progressing = stage_job(db, owner.id, staged_key="a.gpx", updated_at=_ago(hours=1))
            finished = stage_job(db, owner.id, status="completed", updated_at=_ago(days=3))
            db.commit()

        scheduled_jobs.fail_stale_ingestion_jobs()

        assert read_job(committed_sessions, progressing.id).status == "pending"
        assert read_job(committed_sessions, finished.id).status == "completed"

    def test_a_backlog_larger_than_one_batch_is_failed_a_batch_per_transaction(
        self, committed_sessions, owner, monkeypatch
    ):
        monkeypatch.setattr(ingestion_service, "_STALE_JOB_BATCH_SIZE", 2)
        with committed_sessions() as db:
            jobs = [stage_job(db, owner.id, updated_at=_ago(hours=30)) for _ in range(5)]
            db.commit()

        scheduled_jobs.fail_stale_ingestion_jobs()

        assert {read_job(committed_sessions, job.id).status for job in jobs} == {"failed"}


class TestStagedBlobSweep:
    def test_an_unreferenced_old_blob_is_removed_and_the_rest_stays(
        self, committed_sessions, owner, storage, tmp_path, platform
    ):
        stage_blob(storage, "orphan.gpx", b"orphan")
        stage_blob(storage, "live.gpx", b"live")
        storage.save("activity_files", "processed/42.fit", b"retained")
        age_stored_objects(tmp_path, 3 * 86400)
        stage_blob(storage, "new.gpx", b"new")
        with committed_sessions() as db:
            stage_job(db, owner.id, staged_key="live.gpx")
            db.commit()

        scheduled_jobs.sweep_stale_staged_blobs()

        assert staged_keys(storage) == ["live.gpx", "new.gpx"]
        assert storage.get("activity_files", "processed/42.fit") == b"retained"

    def test_no_session_stays_open_across_a_storage_call(self, committed_sessions, owner, storage, tmp_path, platform):
        for index in range(3):
            stage_blob(storage, f"orphan-{index}.gpx", b"orphan")
        age_stored_objects(tmp_path, 3 * 86400)
        probe = ConnectionProbe(storage, ("iter_objects", "delete"))

        ingestion_service.sweep_stale_staged_blobs(platform.clock, probe)

        assert len(probe.open_during_calls) >= 4
        assert set(probe.open_during_calls) == {0}


class TestScheduledEntryPoints:
    def test_the_hourly_fan_out_queues_the_refreshes_of_linked_users(
        self, owner, stub_provider, pool, committed_sessions
    ):
        stub_provider.link(owner.id, activity_gpx())

        scheduled_jobs.enqueue_provider_refreshes()
        pool.drain()

        assert len(activities_of(committed_sessions, owner.id)) == 1

    def test_the_redispatch_queues_the_deferred_refreshes_whose_wait_is_over(
        self, owner, stub_provider, pool, committed_sessions
    ):
        stub_provider.link(owner.id)
        with committed_sessions() as db:
            due = stage_job(db, owner.id, kind=_Kind.REFRESH, status="deferred", retry_after=_ago(minutes=1))
            db.commit()

        scheduled_jobs.redispatch_deferred_refreshes()
        pool.drain()

        assert read_job(committed_sessions, due.id).status == "completed"

    def test_every_recurring_pass_holds_a_lock_of_its_own(self):
        locks = [job.lock_name for job in scheduled_jobs.recurring_jobs()]

        assert None not in locks
        assert len(set(locks)) == len(locks)


def _resume(storage) -> int:
    """Run the startup pass as startup does, returning how many jobs it submitted."""
    return ingestion_service.resume_orphaned_local_jobs(storage, bulk.run_bulk_import_job)


class TestJobsLostWithThePool:
    """A restart loses the in-process pool's uploads and bulk imports, so the local profile runs them again."""

    @pytest.fixture(autouse=True)
    def _single_process(self, monkeypatch):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 1)

    def test_pending_and_processing_uploads_and_a_staged_bulk_import_run_again(
        self, owner, pool, storage, committed_sessions
    ):
        stage_blob(storage, "one.gpx", activity_gpx(name="First"))
        stage_blob(storage, "two.gpx", activity_gpx(name="Second", start=datetime(2026, 2, 1, 8, tzinfo=UTC)))
        archive_key = f"bulk-{uuid.uuid4()}.zip"
        stage_blob(storage, archive_key, zip_of({"c.gpx": activity_gpx(start=datetime(2026, 3, 1, 8, tzinfo=UTC))}))
        with committed_sessions() as db:
            pending = stage_job(db, owner.id, staged_key="one.gpx")
            processing = stage_job(db, owner.id, status="processing", staged_key="two.gpx")
            bulk_job = stage_job(
                db,
                owner.id,
                kind=_Kind.BULK_IMPORT,
                status="processing",
                staged_key=archive_key,
                import_source="generic",
                files_total=1,
            )
            db.commit()

        count = _resume(storage)
        pool.drain()

        assert count == 3
        assert [read_job(committed_sessions, job.id).status for job in (pending, processing, bulk_job)] == [
            "completed"
        ] * 3
        assert len(activities_of(committed_sessions, owner.id)) == 3
        assert staged_keys(storage) == []

    def test_a_folder_import_that_was_still_being_packed_is_failed(self, owner, storage, pool, committed_sessions):
        with committed_sessions() as db:
            packing = stage_job(db, owner.id, kind=_Kind.BULK_IMPORT, import_source="generic")
            db.commit()

        count = _resume(storage)

        row = read_job(committed_sessions, packing.id)
        assert (count, row.status, row.error_code) == (0, "failed", "processing_failed")

    def test_finished_and_refresh_jobs_are_not_run_again(self, owner, storage, pool, committed_sessions):
        with committed_sessions() as db:
            done = stage_job(db, owner.id, status="completed")
            refresh = stage_job(db, owner.id, kind=_Kind.REFRESH)
            db.commit()

        assert _resume(storage) == 0
        assert read_job(committed_sessions, done.id).status == "completed"
        assert read_job(committed_sessions, refresh.id).status == "pending"

    def test_a_job_the_full_pool_turns_away_is_failed_without_stopping_the_others(
        self, owner, storage, committed_sessions, monkeypatch
    ):
        stage_blob(storage, "one.gpx", activity_gpx())
        stage_blob(storage, "two.gpx", activity_gpx())
        release = threading.Event()
        full = core_local_pool.BoundedPool("full", workers=1, max_pending=1)
        monkeypatch.setattr(ingestion_background, "_pool", full)
        full.submit(release.wait, 10)
        with committed_sessions() as db:
            first = stage_job(db, owner.id, staged_key="one.gpx")
            second = stage_job(db, owner.id, staged_key="two.gpx")
            db.commit()
        try:
            count = _resume(storage)
        finally:
            release.set()
            full.shutdown(wait=True)

        assert count == 0
        assert {read_job(committed_sessions, job.id).status for job in (first, second)} == {"failed"}

    @pytest.mark.parametrize("status", ["pending", "processing"])
    def test_a_durable_worker_keeps_its_leased_jobs(self, owner, storage, committed_sessions, monkeypatch, status):
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)
        with committed_sessions() as db:
            job = stage_job(db, owner.id, status=status, staged_key="a.gpx")
            db.commit()

        assert _resume(storage) == 0
        assert read_job(committed_sessions, job.id).status == status

    def test_a_sibling_web_workers_jobs_are_left_alone(self, owner, storage, committed_sessions, monkeypatch):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 2)
        with committed_sessions() as db:
            job = stage_job(db, owner.id, status="processing", staged_key="a.gpx")
            db.commit()

        assert _resume(storage) == 0
        assert read_job(committed_sessions, job.id).status == "processing"


class TestNoSessionAcrossAProviderCall:
    def test_the_probe_sees_a_session_that_is_inside_a_transaction(self, committed_sessions, storage):
        probe = ConnectionProbe(storage, ())

        with committed_sessions() as db:
            db.execute(text("SELECT 1"))
            assert probe.open_sessions() == 1
        assert probe.open_sessions() == 0

    def test_a_refresh_holds_no_database_session_while_the_providers_run(
        self, owner, stub_provider, committed_sessions, storage
    ):
        probe = ConnectionProbe(storage, ())
        seen: list[int] = []
        stub_provider.on_fetch = lambda: seen.append(probe.open_sessions())
        stub_provider.link(owner.id)
        with committed_sessions() as db:
            job = stage_job(db, owner.id, kind=_Kind.REFRESH)
            db.commit()

        ingestion_service.run_refresh_job(job.id, storage)

        assert seen == [0]
        assert read_job(committed_sessions, job.id).status == "completed"


class TestTheStartupPassAsStartupRunsIt:
    def test_resumes_the_lost_uploads_on_the_pool_without_waiting_for_them(
        self, owner, pool, storage, committed_sessions, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 1)
        stage_blob(storage, "one.gpx", activity_gpx())
        with committed_sessions() as db:
            job = stage_job(db, owner.id, staged_key="one.gpx")
            db.commit()

        scheduled_jobs.resume_orphaned_local_jobs()
        pool.drain()

        assert read_job(committed_sessions, job.id).status == "completed"

    def test_fails_the_refreshes_the_lost_pool_held(self, owner, committed_sessions, monkeypatch):
        monkeypatch.setattr(core_config.settings, "WEB_WORKERS", 1)
        with committed_sessions() as db:
            job = stage_job(db, owner.id, kind=_Kind.REFRESH, status="processing")
            db.commit()

        scheduled_jobs.fail_orphaned_local_refreshes()

        assert read_job(committed_sessions, job.id).status == "failed"
