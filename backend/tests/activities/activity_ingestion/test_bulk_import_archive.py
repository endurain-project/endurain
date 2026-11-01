"""Bulk import: one job over one staged archive, worked through in batches.

These run the real archive, storage and job rows; only the per-file pipeline is
replaced, because what is under test is the orchestration around it: what is staged,
what is counted, where a batch stops, and what survives a crash.
"""

import logging
import os
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.storage_local import LocalStorage
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity_ingestion.bulk_import_service as bulk
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_ingestion.service as ingestion_service
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service

_USER = 7


def _commit_through(*_args, **kwargs):
    """Stand in for the publisher: it owns the commit, so the row lands with the event."""
    kwargs["commit"]()


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    ensure_user(session_factory, _USER)
    yield session_factory
    session_factory.kw["bind"].dispose()


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(base_dir=str(tmp_path / "storage"), url_prefix="/files")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, factory, monkeypatch):
    """Point every session, directory and registry at this test."""
    monkeypatch.setattr(bulk.core_database, "SessionLocal", factory)
    monkeypatch.setattr(bulk.core_config, "FILES_UPLOAD_INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setattr(bulk.core_config, "bulk_import_dir_for", lambda user_id: str(tmp_path / "drop" / str(user_id)))
    provider_registry.clear()
    yield
    provider_registry.clear()


def _zip(tmp_path: Path, members: dict[str, bytes], name: str = "export.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return path


def _saver(archive: Path):
    """An ``UploadSaver`` that 'receives' a prepared archive."""

    def save(*, kind, upload_dir, filename):
        os.makedirs(upload_dir, exist_ok=True)
        destination = Path(upload_dir) / filename
        destination.write_bytes(archive.read_bytes())
        return str(destination)

    return save


def _job(factory, job_id: str):
    with factory() as db:
        row = db.get(ingestion_models.ActivityIngestionJob, job_id)
        db.expunge(row)
        return row


def _only_job_id(factory) -> str:
    with factory() as db:
        return db.query(ingestion_models.ActivityIngestionJob).one().id


@pytest.fixture
def pipeline():
    """Replace the per-file pipeline; record which files reached it, in order."""
    seen: list[str] = []

    def fake(user_id, file_path, db, *, source, storage):
        name = os.path.basename(file_path)
        if name.startswith("bad"):
            raise ValueError("unparseable")
        seen.append(name)
        return []

    with patch.object(bulk.activity_ingestion_pipeline_service, "validate_prepare_and_store_file", side_effect=fake):
        yield seen


class TestAcceptArchive:
    def test_stages_the_archive_and_records_an_import_over_it(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"x", "nested/b.gpx": b"y", "readme.txt": b"z"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ) as publish,
        ):
            job = bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())

        assert job.kind is ingestion_constants.IngestionJobKind.BULK_IMPORT
        assert (job.import_source, job.files_total, job.files_done, job.files_failed) == ("generic", 2, 0, 0)
        row = _job(factory, job.id)
        # The archive is the only thing that travelled: held in storage under the job's key.
        assert storage.exists(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, f"upload_staging/{row.staged_key}")
        publish.assert_called_once()
        # Nothing is left in the incoming directory.
        assert not list((tmp_path / "incoming").iterdir())

    def test_a_second_import_while_one_runs_is_a_conflict(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"x"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ),
        ):
            bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())
            with pytest.raises(core_exceptions.ConflictError):
                bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())

    def test_the_database_decides_when_two_requests_race_the_check(self, tmp_path, factory, storage):
        """Both pass the service's check; the partial unique index lets only one row in."""
        archive = _zip(tmp_path, {"a.fit": b"x"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ),
        ):
            bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())
            with patch.object(bulk, "_ensure_none_running"), pytest.raises(core_exceptions.ConflictError):
                bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())

        # The loser's staged archive did not stay behind.
        with factory() as db:
            keys = [row.staged_key for row in db.query(ingestion_models.ActivityIngestionJob).all()]
        staged = list(storage.iter_objects(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "upload_staging/"))
        assert len(staged) == len(keys) == 1

    def test_an_archive_with_nothing_importable_is_refused_and_not_kept(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"notes.txt": b"x"})

        with pytest.raises(core_exceptions.InvalidInputError):
            bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())

        assert list(storage.iter_objects(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "")) == []
        assert not list((tmp_path / "incoming").iterdir())

    def test_only_a_zip_is_accepted(self, tmp_path, factory, storage):
        with pytest.raises(core_exceptions.InvalidInputError):
            bulk.accept_archive(_USER, "ride.fit", MagicMock(), "generic", storage, factory())

    def test_an_unknown_source_is_refused(self, tmp_path, factory, storage):
        with pytest.raises(core_exceptions.InvalidInputError):
            bulk.accept_archive(_USER, "export.zip", MagicMock(), "polar", storage, factory())


class TestRunLocally:
    """Without durable jobs there is no queue to yield to: one unbudgeted pass."""

    def _accept(self, tmp_path, factory, storage, members):
        archive = _zip(tmp_path, members)
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            job = bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory())
        return job.id

    def test_every_file_is_imported_and_the_archive_removed(self, tmp_path, factory, storage, pipeline):
        job_id = self._accept(tmp_path, factory, storage, {"a.fit": b"1", "b.gpx": b"2", "c.tcx": b"3"})

        with patch.object(bulk.core_config.settings, "JOBS_ENABLED", False):
            bulk.run_bulk_import_job(job_id, storage)

        row = _job(factory, job_id)
        assert (row.status, row.files_done, row.files_failed) == ("completed", 3, 0)
        assert pipeline == ["a.fit", "b.gpx", "c.tcx"]
        assert row.staged_key is None
        assert list(storage.iter_objects(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "")) == []

    def test_one_bad_file_is_counted_kept_and_does_not_stop_the_rest(self, tmp_path, factory, storage, pipeline):
        job_id = self._accept(tmp_path, factory, storage, {"a.fit": b"1", "bad.fit": b"BAD", "c.fit": b"3"})

        with patch.object(bulk.core_config.settings, "JOBS_ENABLED", False):
            bulk.run_bulk_import_job(job_id, storage)

        row = _job(factory, job_id)
        # A finished import with failures is still completed; the counters say how many.
        assert (row.status, row.files_done, row.files_failed) == ("completed", 2, 1)
        assert pipeline == ["a.fit", "c.fit"]
        kept = f"{_USER}/{job_id}/bad.fit"
        assert storage.get(ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA, kept) == b"BAD"

    def test_a_file_name_repeated_in_two_folders_is_imported_twice(self, tmp_path, factory, storage, pipeline):
        job_id = self._accept(tmp_path, factory, storage, {"2023/ride.fit": b"1", "2024/ride.fit": b"2"})

        with patch.object(bulk.core_config.settings, "JOBS_ENABLED", False):
            bulk.run_bulk_import_job(job_id, storage)

        assert pipeline == ["ride.fit", "ride.fit"]


class TestBatches:
    """On the durable profile a batch yields: it records progress and queues the next."""

    def _accept(self, tmp_path, factory, storage, members):
        archive = _zip(tmp_path, members)
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ),
        ):
            return bulk.accept_archive(_USER, "export.zip", _saver(archive), "generic", storage, factory()).id

    def test_a_batch_stops_at_its_budget_and_queues_its_continuation(self, tmp_path, factory, storage, pipeline):
        job_id = self._accept(tmp_path, factory, storage, {f"{n}.fit": b"x" for n in "abcde"})

        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk, "_BATCH_MAX_FILES", 2),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ) as publish,
        ):
            bulk.run_bulk_import_job(job_id, storage)

        row = _job(factory, job_id)
        assert (row.status, row.files_done, row.cursor) == ("pending", 2, "b.fit")
        assert pipeline == ["a.fit", "b.fit"]
        # The progress and the continuation are one transaction.
        publish.assert_called_once()
        assert publish.call_args.args[1] == {"job_id": job_id}
        assert storage.exists(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, f"upload_staging/{row.staged_key}")

    def test_the_next_batch_resumes_after_the_cursor_and_finishes(self, tmp_path, factory, storage, pipeline):
        job_id = self._accept(tmp_path, factory, storage, {f"{n}.fit": b"x" for n in "abcde"})

        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk, "_BATCH_MAX_FILES", 2),
            patch.object(
                bulk.activity_ingestion_event_publishers.platform_publisher,
                "publish_committing",
                side_effect=_commit_through,
            ),
        ):
            for _ in range(3):
                bulk.run_bulk_import_job(job_id, storage)

        row = _job(factory, job_id)
        assert (row.status, row.files_done, row.files_failed) == ("completed", 5, 0)
        # Each file exactly once, in order, however the batches fell.
        assert pipeline == ["a.fit", "b.fit", "c.fit", "d.fit", "e.fit"]
        assert list(storage.iter_objects(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "")) == []

    def test_a_repeated_continuation_of_a_finished_import_does_nothing(self, tmp_path, factory, storage, pipeline):
        job_id = self._accept(tmp_path, factory, storage, {"a.fit": b"x"})
        with patch.object(bulk.core_config.settings, "JOBS_ENABLED", True):
            bulk.run_bulk_import_job(job_id, storage)
            bulk.run_bulk_import_job(job_id, storage)

        assert pipeline == ["a.fit"]

    def test_a_continuation_that_raises_leaves_the_cursor_for_the_retry(self, tmp_path, factory, storage):
        job_id = self._accept(tmp_path, factory, storage, {"a.fit": b"x"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", True),
            patch.object(bulk, "_import_member", side_effect=RuntimeError("storage down")),
            pytest.raises(RuntimeError),
        ):
            bulk.run_bulk_import_job(job_id, storage)

        # Durable: the runner retries it, so it is not closed here, and it is
        # released so the retry can claim it.
        assert _job(factory, job_id).status == "pending"


class TestProviderFormat:
    def _register(self, build_source):
        provider_registry.register_bulk_format(
            ingestion_contracts.BulkImportFormat(
                name="acme",
                is_activity_member=lambda name: name.startswith("activities/") and name.endswith(".fit"),
                is_export_member=lambda name: True,
                drop_directory=lambda user_id: f"/nowhere/{user_id}",
                build_source=build_source,
            )
        )

    def test_only_the_formats_activity_members_are_imported_and_it_can_read_the_rest(
        self, tmp_path, factory, storage, pipeline
    ):
        read: dict[str, bytes | None] = {}

        def build_source(user_id, initiated, read_member):
            read["manifest"] = read_member("manifest.csv")
            read["missing"] = read_member("nope")
            return ingestion_contracts.BulkImportSource(import_initiated_time=initiated, user_id=user_id)

        self._register(build_source)
        archive = _zip(tmp_path, {"manifest.csv": b"m", "activities/a.fit": b"1", "media/p.jpg": b"2", "b.fit": b"3"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            job = bulk.accept_archive(_USER, "export.zip", _saver(archive), "acme", storage, factory())
            bulk.run_bulk_import_job(job.id, storage)

        assert job.files_total == 1
        assert pipeline == ["a.fit"]
        assert read == {"manifest": b"m", "missing": None}

    def test_an_archive_that_is_not_a_valid_export_fails_the_job_with_a_specific_code(
        self, tmp_path, factory, storage, pipeline
    ):
        def build_source(*_args):
            raise core_exceptions.InvalidInputError("The export has no manifest")

        self._register(build_source)
        archive = _zip(tmp_path, {"activities/a.fit": b"1"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"),
        ):
            job = bulk.accept_archive(_USER, "export.zip", _saver(archive), "acme", storage, factory())
            bulk.run_bulk_import_job(job.id, storage)

        row = _job(factory, job.id)
        assert (row.status, row.error_code) == ("failed", "invalid_file")
        assert pipeline == []
        assert row.staged_key is None


class TestFromFolder:
    def _folder(self, tmp_path, files: dict[str, bytes]) -> Path:
        folder = tmp_path / "drop" / str(_USER)
        for name, data in files.items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return folder

    def test_an_empty_folder_is_refused_before_a_job_exists(self, tmp_path, factory, storage):
        with pytest.raises(core_exceptions.InvalidInputError):
            bulk.start_from_directory(_USER, "generic", storage, factory())

        with factory() as db:
            assert db.query(ingestion_models.ActivityIngestionJob).count() == 0

    def test_a_full_pool_closes_the_folder_job_so_the_user_can_try_again(self, tmp_path, factory, storage):
        folder = self._folder(tmp_path, {"a.fit": b"1"})
        with (
            patch.object(
                bulk.activity_ingestion_dispatch_service.activity_ingestion_background,
                "submit",
                side_effect=core_local_pool.PoolFullError("full"),
            ),
            pytest.raises(core_local_pool.PoolFullError),
        ):
            bulk.start_from_directory(_USER, "generic", storage, factory())

        with factory() as db:
            row = db.query(ingestion_models.ActivityIngestionJob).one()
        assert (row.status, row.error_code) == ("failed", "processing_failed")
        assert (folder / "a.fit").exists()

    def test_the_folder_is_packed_staged_and_only_then_consumed(self, tmp_path, factory, storage, pipeline):
        folder = self._folder(tmp_path, {"a.fit": b"1", "sub/b.gpx": b"2", "notes.txt": b"n"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit") as submit,
        ):
            job = bulk.start_from_directory(_USER, "generic", storage, factory())
            # The request returned the handle without touching the files.
            assert (folder / "a.fit").exists()
            run, *args = submit.call_args.args
            run(*args)

        row = _job(factory, job.id)
        assert (row.status, row.files_done, row.files_total) == ("completed", 2, 2)
        assert pipeline == ["a.fit", "b.gpx"]
        assert not (folder / "a.fit").exists()
        assert not (folder / "sub" / "b.gpx").exists()
        # What is not part of the export is not the import's business: left where it was.
        assert (folder / "notes.txt").exists()

    def test_a_failure_staging_leaves_the_users_files_where_they_were(self, tmp_path, factory, storage, pipeline):
        folder = self._folder(tmp_path, {"a.fit": b"1"})
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit") as submit,
        ):
            job = bulk.start_from_directory(_USER, "generic", storage, factory())
            with patch.object(storage, "save_stream", side_effect=RuntimeError("bucket down")):
                run, *args = submit.call_args.args
                run(*args)

        row = _job(factory, job.id)
        assert (row.status, row.error_code) == ("failed", "processing_failed")
        assert (folder / "a.fit").exists()

    def test_another_users_folder_is_neither_imported_nor_consumed(self, tmp_path, factory, storage, pipeline):
        mine = self._folder(tmp_path, {"mine.fit": b"1"})
        other = tmp_path / "drop" / str(_USER + 1)
        other.mkdir(parents=True)
        (other / "theirs.fit").write_bytes(b"2")
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit") as submit,
        ):
            bulk.start_from_directory(_USER, "generic", storage, factory())
            run, *args = submit.call_args.args
            run(*args)

        assert pipeline == ["mine.fit"]
        assert not (mine / "mine.fit").exists()
        assert (other / "theirs.fit").exists()

    def test_a_symlink_in_the_folder_is_not_packed(self, tmp_path, factory, storage, pipeline):
        secret = tmp_path / "secret.fit"
        secret.write_bytes(b"outside")
        folder = self._folder(tmp_path, {"a.fit": b"1"})
        os.symlink(secret, folder / "link.fit")
        with (
            patch.object(bulk.core_config.settings, "JOBS_ENABLED", False),
            patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit") as submit,
        ):
            bulk.start_from_directory(_USER, "generic", storage, factory())
            run, *args = submit.call_args.args
            run(*args)

        assert pipeline == ["a.fit"]
        assert secret.exists()

    def test_a_second_import_while_one_is_running_is_a_conflict(self, tmp_path, factory, storage):
        self._folder(tmp_path, {"a.fit": b"1"})
        with patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"):
            bulk.start_from_directory(_USER, "generic", storage, factory())
            with pytest.raises(core_exceptions.ConflictError):
                bulk.start_from_directory(_USER, "generic", storage, factory())


class TestLostFolderPack:
    """A folder import whose packing was lost mid-way frees the user's slot soon, not after a day."""

    def _folder_job(self, factory, storage, tmp_path, *, idle_minutes: int) -> str:
        folder = tmp_path / "drop" / str(_USER)
        folder.mkdir(parents=True)
        (folder / "a.fit").write_bytes(b"1")
        with patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"):
            job = bulk.start_from_directory(_USER, "generic", storage, factory())
        stamp = datetime.now(UTC) - timedelta(minutes=idle_minutes)
        with factory() as db:
            db.get(ingestion_models.ActivityIngestionJob, job.id).updated_at = stamp
            db.commit()
        return job.id

    def _reap(self, factory, storage) -> None:
        platform = MagicMock()
        platform.clock.now.return_value = datetime.now(UTC)
        with patch.object(ingestion_service.core_database, "SessionLocal", factory):
            ingestion_service.fail_stale_ingestion_jobs(platform.clock, storage)

    def test_a_pack_that_stopped_beating_is_failed_so_the_user_can_import_again(self, tmp_path, factory, storage):
        job_id = self._folder_job(factory, storage, tmp_path, idle_minutes=60)

        self._reap(factory, storage)

        assert _job(factory, job_id).status == "failed"
        with factory() as db:
            assert ingestion_crud.get_active_bulk_import_job_id(_USER, db) is None

    def test_a_pack_that_is_still_beating_is_left_running(self, tmp_path, factory, storage):
        job_id = self._folder_job(factory, storage, tmp_path, idle_minutes=1)

        self._reap(factory, storage)

        assert _job(factory, job_id).status == "pending"

    def test_a_staged_import_waiting_in_the_queue_is_not_failed_early(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"1"})
        with patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"):
            job = bulk.accept_archive(_USER, "x.zip", _saver(archive), "generic", storage, factory())
        with factory() as db:
            db.get(ingestion_models.ActivityIngestionJob, job.id).updated_at = datetime.now(UTC) - timedelta(hours=2)
            db.commit()

        self._reap(factory, storage)

        assert _job(factory, job.id).status == "pending"

    def test_packing_keeps_the_job_beating(self, tmp_path, factory, storage):
        job_id = self._folder_job(factory, storage, tmp_path, idle_minutes=60)
        before = _job(factory, job_id).updated_at

        with patch.object(bulk, "_HEARTBEAT_SECONDS", 0.01), bulk._heartbeat(job_id):
            deadline = time.monotonic() + 5
            while _job(factory, job_id).updated_at == before and time.monotonic() < deadline:
                time.sleep(0.02)

        assert _job(factory, job_id).updated_at != before

    def test_a_pack_finishing_after_the_job_was_failed_neither_imports_nor_consumes_the_files(
        self, tmp_path, factory, storage, pipeline
    ):
        job_id = self._folder_job(factory, storage, tmp_path, idle_minutes=60)
        self._reap(factory, storage)
        folder = tmp_path / "drop" / str(_USER)

        with patch.object(bulk.core_config.settings, "JOBS_ENABLED", False):
            bulk.feed_archive_from_directory(job_id, _USER, "generic", str(folder), storage)

        assert (folder / "a.fit").exists()
        assert pipeline == []
        assert _job(factory, job_id).status == "failed"
        assert not storage.exists(
            upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
            upload_entry_service.upload_staging_storage_key(f"bulk-{job_id}.zip"),
        )


class TestNoConnectionHeldWhileStoring:
    """A request's session holds a pooled connection once it has read, so storage writes must follow the commit."""

    def test_the_archive_is_staged_after_the_running_check_has_ended_its_transaction(self):
        db = MagicMock()
        order = MagicMock()
        order.attach_mock(db.commit, "commit")
        save_upload = MagicMock(side_effect=RuntimeError("stop here"))
        order.attach_mock(save_upload, "save_upload")

        with (
            patch.object(bulk.activity_ingestion_dispatch_service, "require_capacity"),
            patch.object(bulk.activity_ingestion_crud, "get_active_bulk_import_job_id", return_value=None),
            pytest.raises(RuntimeError, match="stop here"),
        ):
            bulk.accept_archive(_USER, "export.zip", save_upload, "generic", MagicMock(), db)

        assert [call[0] for call in order.mock_calls] == ["commit", "save_upload"]


class TestFailureLogLevels:
    """A user's bad file is a warning; a failure the operator must act on is an error."""

    @staticmethod
    def _member(tmp_path):
        path = tmp_path / "export.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a.fit", b"x")
        return zipfile.ZipFile(path)

    def _import(self, tmp_path, caplog, error):
        with (
            caplog.at_level(logging.DEBUG, logger=bulk.logger.name),
            self._member(tmp_path) as archive,
            patch.object(
                bulk.activity_ingestion_pipeline_service, "validate_prepare_and_store_file", side_effect=error
            ),
            patch.object(bulk, "_keep_failed_member"),
        ):
            assert bulk._import_member(archive, "a.fit", _USER, MagicMock(), "job-1", MagicMock()) is False
        return [record for record in caplog.records if record.levelno >= logging.WARNING]

    @pytest.mark.parametrize(
        "error",
        [
            core_exceptions.InvalidInputError("not a fit file"),
            core_exceptions.UnsupportedFormatError("format"),
            core_exceptions.PayloadTooLargeError("big"),
            core_exceptions.ConflictError("duplicate"),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_a_file_the_pipeline_refuses_is_a_warning_without_a_traceback(self, tmp_path, caplog, error):
        records = self._import(tmp_path, caplog, error)

        assert [record.levelno for record in records] == [logging.WARNING]
        assert records[0].exc_info is None

    @pytest.mark.parametrize(
        "error",
        [RuntimeError("storage down"), core_exceptions.ProcessingError("failed to save")],
        ids=lambda error: type(error).__name__,
    )
    def test_an_internal_failure_is_an_error_with_a_traceback(self, tmp_path, caplog, error):
        records = self._import(tmp_path, caplog, error)

        assert [record.levelno for record in records] == [logging.ERROR]
        assert records[0].exc_info is not None

    def _feed(self, caplog, error):
        with (
            caplog.at_level(logging.DEBUG, logger=bulk.logger.name),
            patch.object(bulk, "resolve_format", return_value=MagicMock()),
            patch.object(bulk, "_pack_directory", side_effect=error),
            patch.object(bulk.activity_ingestion_service, "fail_ingestion_job"),
        ):
            bulk.feed_archive_from_directory("job-1", _USER, "strava", "/nowhere", MagicMock())
        return [record for record in caplog.records if record.levelno >= logging.WARNING]

    def test_a_folder_the_user_filled_wrongly_is_a_warning(self, caplog):
        records = self._feed(caplog, core_exceptions.InvalidInputError("Invalid ZIP archive"))

        assert [record.levelno for record in records] == [logging.WARNING]
        assert records[0].exc_info is None

    def test_a_staging_failure_is_an_error(self, caplog):
        records = self._feed(caplog, OSError("disk full"))

        assert [record.levelno for record in records] == [logging.ERROR]
