"""Idempotency-Key on a bulk import, and the 409 that names the import already running.

These run the real archive, storage and job rows, like ``test_bulk_import_archive``; only the publisher is
stood in for.
"""

import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from jasil.backends.storage_local import LocalStorage
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.activities.activity_ingestion.bulk_import_service as bulk
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service

_USER = 7


def _commit_through(*_args, **kwargs):
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
    monkeypatch.setattr(bulk.core_database, "SessionLocal", factory)
    monkeypatch.setattr(bulk.core_config, "FILES_UPLOAD_INCOMING_DIR", str(tmp_path / "incoming"))
    monkeypatch.setattr(bulk.core_config, "bulk_import_dir_for", lambda user_id: str(tmp_path / "drop" / str(user_id)))
    monkeypatch.setattr(bulk.core_config.settings, "JOBS_ENABLED", True)
    with patch.object(
        bulk.activity_ingestion_event_publishers.platform_publisher,
        "publish_committing",
        side_effect=_commit_through,
    ) as publish:
        yield publish


def _zip(tmp_path: Path, members: dict[str, bytes], name: str = "export.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        for member, data in members.items():
            archive.writestr(member, data)
    return path


def _saver(archive: Path):
    def save(*, kind, upload_dir, filename):
        os.makedirs(upload_dir, exist_ok=True)
        destination = Path(upload_dir) / filename
        destination.write_bytes(archive.read_bytes())
        return str(destination)

    return save


def _jobs(factory) -> list[ingestion_models.ActivityIngestionJob]:
    with factory() as db:
        rows = db.query(ingestion_models.ActivityIngestionJob).all()
        db.expunge_all()
        return rows


def _accept(factory, storage, archive: Path, *, key: str | None = None, source: str = "generic"):
    return bulk.accept_archive(_USER, "export.zip", _saver(archive), source, storage, factory(), idempotency_key=key)


class TestIdempotencyKey:
    def test_the_key_and_a_fingerprint_are_stored_with_the_job(self, tmp_path, factory, storage):
        job = _accept(factory, storage, _zip(tmp_path, {"a.fit": b"x"}), key="key-1")

        (row,) = _jobs(factory)
        assert row.id == job.id
        assert (row.idempotency_key, row.kind) == ("key-1", ingestion_constants.IngestionJobKind.BULK_IMPORT.value)
        assert row.request_fingerprint is not None and len(row.request_fingerprint) == 64

    def test_no_key_stores_none(self, tmp_path, factory, storage):
        _accept(factory, storage, _zip(tmp_path, {"a.fit": b"x"}))

        (row,) = _jobs(factory)
        assert (row.idempotency_key, row.request_fingerprint) == (None, None)

    def test_a_replay_returns_the_original_job_without_staging_or_queueing_again(
        self, tmp_path, factory, storage, _isolated
    ):
        archive = _zip(tmp_path, {"a.fit": b"x"})
        first = _accept(factory, storage, archive, key="key-1")

        # The first import is still the one running: a replay is answered with it, not refused.
        replay = _accept(factory, storage, archive, key="key-1")

        assert replay.id == first.id
        assert len(_jobs(factory)) == 1
        _isolated.assert_called_once()
        assert len(list(storage.iter_objects(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "upload_staging/"))) == 1
        # The replayed upload did not stay in the incoming directory.
        assert not list((tmp_path / "incoming").iterdir())

    def test_a_replay_of_a_finished_import_returns_it_in_its_current_state(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"x"})
        first = _accept(factory, storage, archive, key="key-1")
        with factory() as db:
            row = db.get(ingestion_models.ActivityIngestionJob, first.id)
            row.status = "completed"
            row.completed_at = datetime.now(UTC)
            db.commit()

        replay = _accept(factory, storage, archive, key="key-1")

        assert (replay.id, replay.status) == (first.id, core_job_status.JobState.SUCCEEDED)
        assert len(_jobs(factory)) == 1

    def test_the_same_key_with_a_different_archive_is_refused(self, tmp_path, factory, storage):
        _accept(factory, storage, _zip(tmp_path, {"a.fit": b"x"}), key="key-1")

        with pytest.raises(core_exceptions.ConflictError, match="Idempotency-Key"):
            _accept(factory, storage, _zip(tmp_path, {"b.fit": b"y"}, "other.zip"), key="key-1")

        assert len(_jobs(factory)) == 1
        assert not list((tmp_path / "incoming").iterdir())

    def test_the_same_archive_read_as_another_source_is_another_request(self, tmp_path):
        archive = _zip(tmp_path, {"a.fit": b"x"})

        generic = bulk._request_fingerprint(str(archive), "generic")

        assert generic == bulk._request_fingerprint(str(archive), "generic")
        assert generic != bulk._request_fingerprint(str(archive), "strava")

    def test_a_different_key_while_an_import_runs_is_still_a_conflict(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"x"})
        _accept(factory, storage, archive, key="key-1")

        with pytest.raises(core_exceptions.ConflictError):
            _accept(factory, storage, archive, key="key-2")

    def test_a_key_is_scoped_to_bulk_imports(self, tmp_path, factory, storage):
        """An upload that used the key does not make the import a replay: the constraint is per kind."""
        archive = _zip(tmp_path, {"a.fit": b"x"})
        with factory() as db:
            db.add(
                ingestion_models.ActivityIngestionJob(
                    id="6d9d2f4a-0000-4000-8000-000000000001",
                    user_id=_USER,
                    kind="upload",
                    idempotency_key="key-1",
                    request_fingerprint="0" * 64,
                    status="completed",
                )
            )
            db.commit()

        job = _accept(factory, storage, archive, key="key-1")

        assert job.kind == "activity_bulk_import"

    def test_two_requests_racing_with_the_same_key_return_the_winner(self, tmp_path, factory, storage):
        """Both passed the lookup; the unique key decides, and the loser answers with the winner's job."""
        archive = _zip(tmp_path, {"a.fit": b"x"})
        first = _accept(factory, storage, archive, key="key-1")

        winner = bulk.activity_ingestion_crud.get_job_for_idempotency(
            "key-1", _USER, ingestion_constants.IngestionJobKind.BULK_IMPORT, factory()
        )
        # The first lookup (before the check) sees nothing, as it would for a request that raced the winner.
        with (
            patch.object(bulk.activity_ingestion_crud, "get_job_for_idempotency", side_effect=[None, winner]),
            patch.object(bulk, "_ensure_none_running"),
        ):
            replay = _accept(factory, storage, archive, key="key-1")

        assert replay.id == first.id
        assert len(_jobs(factory)) == 1


class TestTheRefusalNamesTheRunningJob:
    def test_an_archive_import_conflict_carries_the_running_job(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"x"})
        first = _accept(factory, storage, archive)

        with pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
            _accept(factory, storage, archive)

        assert refused.value.job_id == first.id
        assert refused.value.extensions == {"job_id": first.id}
        assert refused.value.status_code == 409 and refused.value.code == "conflict"

    def test_a_folder_import_conflict_carries_the_running_job(self, tmp_path, factory, storage):
        drop = tmp_path / "drop" / str(_USER)
        drop.mkdir(parents=True)
        (drop / "a.fit").write_bytes(b"1")
        with patch.object(bulk.activity_ingestion_dispatch_service.activity_ingestion_background, "submit"):
            first = bulk.start_from_directory(_USER, "generic", storage, factory())
            with pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
                bulk.start_from_directory(_USER, "generic", storage, factory())

        assert refused.value.extensions == {"job_id": first.id}

    def test_a_race_lost_at_the_index_names_the_winner(self, tmp_path, factory, storage):
        archive = _zip(tmp_path, {"a.fit": b"x"})
        first = _accept(factory, storage, archive)

        with patch.object(bulk, "_ensure_none_running"), pytest.raises(core_exceptions.JobAlreadyRunningError) as lost:
            _accept(factory, storage, archive)

        assert lost.value.extensions == {"job_id": first.id}

    def test_an_import_that_finished_in_between_is_a_plain_conflict(self):
        refusal = bulk._already_running(None)

        assert type(refusal) is core_exceptions.ConflictError
