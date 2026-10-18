"""Job-state changes survive the session that made them.

The CRUD only stages a transition, and every job opens its own short-lived
session. Closing a session without committing discards the change, which no
mock-based test can see: the failure is a job row that silently stays
``pending`` or ``processing`` forever. These run the real job functions against
a real (SQLite) database and read the row back from a *fresh* session.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from tests._helpers.db import (
    POSTGRES_TEST_URL_ENV,
    create_postgres_session_factory,
    create_sqlite_session_factory,
    drop_postgres_schema,
    ensure_user,
    postgres_test_url,
)

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.service as ingestion_jobs


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def factory(request):
    """The same assertions against SQLite and, when configured, PostgreSQL.

    SQLite shares one connection across sessions, so it can only show that a
    change was committed. PostgreSQL gives each session its own connection and
    transaction, which is what the production job runner has.
    """
    if request.param == "sqlite":
        session_factory = create_sqlite_session_factory()
        try:
            yield session_factory
        finally:
            session_factory.kw["bind"].dispose()
        return

    if postgres_test_url() is None:
        pytest.skip(f"{POSTGRES_TEST_URL_ENV} is not set")
    session_factory = create_postgres_session_factory()
    try:
        yield session_factory
    finally:
        drop_postgres_schema(session_factory)


def _add_job(factory, **overrides) -> None:
    now = datetime.now(UTC)
    values = {
        "id": "job-1",
        "user_id": 7,
        "kind": "upload",
        "status": "pending",
        "staged_key": "abc.gpx",
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    ensure_user(factory, values["user_id"])
    with factory() as db:
        db.add(ingestion_models.ActivityIngestionJob(**values))
        db.commit()


def _read_job(factory, job_id: str = "job-1"):
    """Read through a new session so only committed state is visible."""
    with factory() as db:
        row = db.get(ingestion_models.ActivityIngestionJob, job_id)
        if row is None:
            return None
        return SimpleNamespace(
            status=row.status,
            error_code=row.error_code,
            activity_ids=list(row.activity_ids or []),
            staged_key=row.staged_key,
        )


class TestUploadJob:
    def test_a_successful_import_is_recorded_as_completed(self, factory):
        _add_job(factory)
        created = [SimpleNamespace(id=11), SimpleNamespace(id=12)]
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", return_value=created
            ),
        ):
            ingestion_jobs.run_upload_job("job-1", "storage")

        job = _read_job(factory)
        assert job.status == "completed"
        assert job.activity_ids == [11, 12]
        # Cleared so a retry after success is a no-op rather than a re-import.
        assert job.staged_key is None

    def test_a_file_with_no_activities_is_recorded_as_failed(self, factory):
        _add_job(factory)
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", return_value=[]
            ),
        ):
            ingestion_jobs.run_upload_job("job-1", "storage")

        job = _read_job(factory)
        assert job.status == "failed"
        assert job.error_code == activity_ingestion_constants.IngestionJobErrorCode.NO_ACTIVITIES_FOUND.value

    def test_processing_is_visible_while_the_import_is_still_running(self, factory):
        """``mark_processing`` commits before the (slow) import starts."""
        _add_job(factory)
        seen: list[str] = []

        def _import(*_args, **_kwargs):
            seen.append(_read_job(factory).status)
            return [SimpleNamespace(id=1)]

        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service, "process_staged_upload", side_effect=_import
            ),
        ):
            ingestion_jobs.run_upload_job("job-1", "storage")

        assert seen == ["processing"]

    def test_a_terminal_failure_is_recorded(self, factory):
        _add_job(factory, status="processing")
        with patch.object(ingestion_jobs.core_database, "SessionLocal", factory):
            ingestion_jobs.fail_ingestion_job(
                "job-1",
                activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED,
                MagicMock(),
                staged_key="abc.gpx",
            )

        job = _read_job(factory)
        assert job.status == "failed"
        assert job.error_code == activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED.value


class TestRefreshJob:
    def test_a_refresh_is_recorded_as_completed(self, factory):
        _add_job(factory, kind="refresh", staged_key=None)
        synced = [SimpleNamespace(id=21)]

        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
            patch.object(
                ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers", return_value=synced
            ),
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        job = _read_job(factory)
        assert job.status == "completed"
        assert job.activity_ids == [21]


class TestPrune:
    def test_deleted_rows_stay_deleted(self, factory):
        old = datetime.now(UTC) - timedelta(days=400)
        _add_job(factory, id="old", status="completed", completed_at=old, staged_key=None)
        _add_job(factory, id="fresh", status="pending")

        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = True
        platform.clock.now.return_value = datetime.now(UTC)
        with (
            patch.object(ingestion_jobs.core_config.settings, "JOBS_RETENTION_DAYS", 90),
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
        ):
            ingestion_jobs.prune_expired_ingestion_jobs(platform.lock, platform.clock)

        assert _read_job(factory, "old") is None
        assert _read_job(factory, "fresh") is not None


class TestFinishedJobsAreNotReopened:
    """A duplicate delivery of a finished job's event must not flip it back to processing."""

    def test_a_completed_refresh_is_not_run_again_or_reopened(self, factory):
        done_at = datetime.now(UTC) - timedelta(minutes=5)
        _add_job(factory, kind="refresh", staged_key=None, status="completed", completed_at=done_at, activity_ids=[1])

        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
            patch.object(ingestion_jobs.activity_ingestion_refresh_entry_service, "sync_linked_providers") as sync,
        ):
            ingestion_jobs.run_refresh_job("job-1", "storage")

        sync.assert_not_called()
        job = _read_job(factory)
        assert job.status == "completed"
        assert job.activity_ids == [1]

    def test_a_job_that_is_still_pending_moves_to_processing(self, factory):
        _add_job(factory, kind="refresh", staged_key=None)
        with factory() as db:
            assert ingestion_jobs.activity_ingestion_crud.mark_processing("job-1", db, lease=timedelta(0)) is True
            db.commit()

        assert _read_job(factory).status == "processing"

    def test_a_job_another_worker_is_running_is_not_claimed_twice(self, factory):
        _add_job(factory, kind="refresh", staged_key=None)
        with factory() as db:
            crud = ingestion_jobs.activity_ingestion_crud
            assert crud.mark_processing("job-1", db, lease=timedelta(minutes=5)) is True
            db.commit()
        with factory() as db:
            assert crud.mark_processing("job-1", db, lease=timedelta(minutes=5)) is False

    def test_an_abandoned_claim_can_be_taken_over(self, factory):
        _add_job(factory, kind="refresh", staged_key=None)
        with factory() as db:
            crud = ingestion_jobs.activity_ingestion_crud
            assert crud.mark_processing("job-1", db, lease=timedelta(minutes=5)) is True
            db.commit()
        with factory() as db:
            assert crud.mark_processing("job-1", db, lease=timedelta(minutes=-5)) is True

    def test_a_released_job_can_be_claimed_by_the_retry(self, factory):
        _add_job(factory, kind="refresh", staged_key=None)
        crud = ingestion_jobs.activity_ingestion_crud
        with factory() as db:
            crud.mark_processing("job-1", db, lease=timedelta(minutes=5))
            crud.release_job("job-1", db)
            db.commit()
        with factory() as db:
            assert crud.mark_processing("job-1", db, lease=timedelta(minutes=5)) is True

    def test_an_unknown_job_is_reported_as_not_runnable(self, factory):
        with factory() as db:
            assert ingestion_jobs.activity_ingestion_crud.mark_processing("missing", db, lease=timedelta(0)) is False


class TestFailStaleJobs:
    """Jobs whose work was lost (restart, dead loop) end terminal instead of ``pending`` forever."""

    @staticmethod
    def _run(factory) -> list[str]:
        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = True
        platform.clock.now.return_value = datetime.now(UTC)
        discarded: list[str] = []
        with (
            patch.object(ingestion_jobs.core_database, "SessionLocal", factory),
            patch.object(
                ingestion_jobs.activity_ingestion_upload_entry_service,
                "discard_staged_upload",
                side_effect=lambda key, _storage: discarded.append(key),
            ),
        ):
            ingestion_jobs.fail_stale_ingestion_jobs(platform.lock, platform.clock, platform.storage)
        return discarded

    def test_an_idle_upload_is_failed_and_its_blob_dropped(self, factory):
        _add_job(factory, updated_at=datetime.now(UTC) - timedelta(hours=25))

        discarded = self._run(factory)

        job = _read_job(factory)
        assert job.status == "failed"
        assert job.error_code == activity_ingestion_constants.IngestionJobErrorCode.PROCESSING_FAILED.value
        assert job.staged_key is None
        assert discarded == ["abc.gpx"]

    def test_an_idle_job_without_a_blob_is_failed(self, factory):
        _add_job(
            factory,
            kind="refresh",
            status="processing",
            staged_key=None,
            updated_at=datetime.now(UTC) - timedelta(hours=25),
        )

        assert self._run(factory) == []
        assert _read_job(factory).status == "failed"

    def test_a_job_still_progressing_is_left_alone(self, factory):
        _add_job(factory, updated_at=datetime.now(UTC) - timedelta(hours=1))

        assert self._run(factory) == []
        assert _read_job(factory).status == "pending"

    def test_a_finished_job_is_left_alone(self, factory):
        old = datetime.now(UTC) - timedelta(days=3)
        _add_job(factory, status="completed", staged_key=None, updated_at=old, completed_at=old)

        self._run(factory)

        assert _read_job(factory).status == "completed"


class TestSweepStaleStagedBlobs:
    """Blobs no live job will read are removed; ones a job still names, and fresh ones, are not."""

    _NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    def _run(self, factory, objects: dict[tuple[str, str], float]) -> list[tuple[str, str]]:
        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = True
        platform.clock.now.return_value = self._NOW
        deleted: list[tuple[str, str]] = []

        def iter_objects(area, prefix=""):
            return iter([(key, ts) for (a, key), ts in objects.items() if a == area and key.startswith(prefix)])

        platform.storage.iter_objects.side_effect = iter_objects
        platform.storage.delete.side_effect = lambda area, key: deleted.append((area, key))
        with patch.object(ingestion_jobs.core_database, "SessionLocal", factory):
            ingestion_jobs.sweep_stale_staged_blobs(platform.lock, platform.clock, platform.storage)
        return deleted

    def _age(self, days: float) -> float:
        return (self._NOW - timedelta(days=days)).timestamp()

    def test_an_unreferenced_old_upload_is_removed(self, factory):
        area = ingestion_jobs.activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA

        deleted = self._run(factory, {(area, "upload_staging/orphan.gpx"): self._age(3)})

        assert deleted == [(area, "upload_staging/orphan.gpx")]

    def test_an_upload_a_job_still_names_is_kept(self, factory):
        _add_job(factory, staged_key="live.gpx")
        area = ingestion_jobs.activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA

        assert self._run(factory, {(area, "upload_staging/live.gpx"): self._age(3)}) == []

    def test_a_recent_upload_is_kept(self, factory):
        area = ingestion_jobs.activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA

        assert self._run(factory, {(area, "upload_staging/new.gpx"): self._age(0.5)}) == []

    def test_retained_activity_files_are_never_touched(self, factory):
        """They share the area, under ``processed/``; only ``upload_staging/`` is scanned."""
        area = ingestion_jobs.activity_ingestion_upload_entry_service.UPLOAD_STAGING_STORAGE_AREA

        assert self._run(factory, {(area, "processed/42.fit"): self._age(90)}) == []
