"""Bulk import: one job over one staged archive, worked through in batches.

These run the real archive, storage and job rows; only the per-file pipeline is
replaced, because what is under test is the orchestration around it: what is staged,
what is counted, where a batch stops, and what survives a crash.
"""

import os
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.storage_local import LocalStorage
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.bulk_import_service as bulk
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.provider_registry as provider_registry
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
        assert storage.get(bulk.BULK_IMPORT_ERROR_STORAGE_AREA, kept) == b"BAD"

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
