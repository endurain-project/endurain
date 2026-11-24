"""A bulk import works through a ZIP of activity files as one job, through the real route, pool, storage and database.

A client posts a real archive (or asks for its server-side folder to be imported); the archive is staged in the
platform storage and one job row tracks it. The local profile runs the whole import on the in-process pool; the durable
profile works it in batches that a worker's handler runs, each continuing the same job.
"""

import logging
import os
import stat
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import jasil.audit.models as audit_models
import jasil.jobs.registry as jobs_registry
import pytest
from jasil.jobs import ContinueJob
from jasil.providers import StorageBackendUnavailableError
from sqlalchemy import select, update

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import modules.activities.activity_ingestion.audit_actions as ingestion_audit_actions
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.bulk_import_service as bulk
import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.contracts as ingestion_contracts
import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_ingestion.service as ingestion_service
import modules.activities.activity_ingestion.subscribers as ingestion_subscribers
from tests._factories.garmin import EMPTY_GPX, activity_gpx
from tests._factories.ingestion import (
    activities_of,
    activity_tcx,
    all_jobs,
    archive_of,
    fit_file,
    queued_events,
    read_job,
    stage_blob,
    stage_job,
    staged_keys,
)
from tests._factories.profile import FaultyStorage

_API = core_config.ROOT_PATH
_BULK = f"{_API}/activities/bulk-import"
_ERRORS = ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA
_Kind = ingestion_constants.IngestionJobKind
_START = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)


@pytest.fixture
def me(make_signed_in):
    """A signed-in regular user."""
    return make_signed_in()


def _ride(day: int, *, name: str = "Ride") -> bytes:
    """A GPX file of a ride on a given day of March 2026, distinct from every other day's."""
    return activity_gpx(start=_START + timedelta(days=day), name=name)


def _import(user, members: dict[str, bytes], *, source: str | None = None, key: str | None = None):
    params = {"source": source} if source else {}
    headers = {"Idempotency-Key": f'"{key}"'} if key else {}
    return user.client.post(_BULK, files={"file": ("export.zip", archive_of(members))}, params=params, headers=headers)


def _drop_folder(user_id: uuid.UUID, files: dict[str, bytes]) -> Path:
    folder = Path(core_config.bulk_import_dir_for(user_id))
    for name, content in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return folder


def _audit_rows(sessions) -> list[audit_models.AuditLog]:
    with sessions() as db:
        return list(
            db.scalars(
                select(audit_models.AuditLog).where(
                    audit_models.AuditLog.action_id == ingestion_audit_actions.IMPORT_REQUEST.id
                )
            )
        )


def _handler():
    return jobs_registry.registry.get(ingestion_subscribers.BULK_IMPORT_SUBSCRIBER_ID)


class TestAnImportedArchive:
    def test_imports_every_activity_file_and_consumes_the_archive(self, me, pool, committed_sessions, storage):
        response = _import(
            me,
            {
                "rides/a.gpx": _ride(1),
                "rides/b.tcx": activity_tcx(start=_START + timedelta(days=2)),
                "c.fit": fit_file(start=_START + timedelta(days=3)),
                "readme.txt": b"not an activity",
            },
        )
        pool.drain()

        assert response.status_code == 202, response.text
        assert response.json()["files_total"] == 3
        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.import_source, row.files_done, row.files_failed) == ("completed", "generic", 3, 0)
        assert row.staged_key is None
        assert len(activities_of(committed_sessions, me.user.id)) == 3
        assert staged_keys(storage) == []
        assert not os.listdir(core_config.FILES_UPLOAD_INCOMING_DIR)

    def test_stamps_each_activity_as_imported(self, me, pool, committed_sessions):
        _import(me, {"a.gpx": _ride(1)})
        pool.drain()

        (activity,) = activities_of(committed_sessions, me.user.id)
        assert activity.import_info["imported"] is True
        assert activity.import_info["import_source"] == "Basic bulk import"

    def test_a_bad_file_is_counted_failed_and_kept_without_stopping_the_rest(
        self, me, pool, committed_sessions, storage, caplog
    ):
        with caplog.at_level(logging.WARNING, logger=bulk.logger.name):
            response = _import(me, {"a.gpx": _ride(1), "bad.gpx": EMPTY_GPX, "c.gpx": _ride(3)})
            pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_done, row.files_failed) == ("completed", 2, 1)
        assert len(activities_of(committed_sessions, me.user.id)) == 2
        kept = f"{ingestion_constants.bulk_import_error_prefix(me.user.id)}{row.id}/bad.gpx"
        assert storage.get(_ERRORS, kept) == EMPTY_GPX
        refusals = [record for record in caplog.records if "could not be imported" in record.getMessage()]
        assert [record.levelno for record in refusals] == [logging.WARNING], "a user's bad file is no error"
        assert refusals[0].exc_info is None

    def test_a_file_name_repeated_in_two_folders_is_imported_twice(self, me, pool, committed_sessions):
        _import(me, {"2023/ride.gpx": _ride(1), "2024/ride.gpx": _ride(2)})
        pool.drain()

        assert len(activities_of(committed_sessions, me.user.id)) == 2

    def test_the_same_content_twice_is_stored_once_but_both_files_count_as_done(self, me, pool, committed_sessions):
        response = _import(me, {"a.gpx": _ride(1), "copy/a.gpx": _ride(1)})
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.files_done, row.files_failed) == (2, 0)
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_tells_the_owner_after_the_outcome_is_committed(self, me, pool, committed_sessions, hints):
        response = _import(me, {"a.gpx": _ride(1)})
        pool.drain()

        assert [hint["message"] for _key, hint in hints] == ["JOB_STATUS_CHANGED"]
        assert read_job(committed_sessions, uuid.UUID(response.json()["id"])).status == "completed"

    def test_is_audited_with_its_file_count(self, me, pool, committed_sessions):
        response = _import(me, {"a.gpx": _ride(1), "nested/b.gpx": _ride(2), "readme.txt": b"z"})
        pool.drain()

        (entry,) = _audit_rows(committed_sessions)
        assert (entry.target_type, entry.target_id, entry.target_owner_id) == (
            "activity_ingestion_job",
            response.json()["id"],
            str(me.user.id),
        )
        assert entry.details == {"source": "archive", "file_count": 2}

    def test_a_storage_outage_fails_the_job_and_drops_the_archive_since_nothing_retries(
        self, me, pool, committed_sessions, storage, break_storage
    ):
        break_storage(open_stream=StorageBackendUnavailableError("storage is down"))

        response = _import(me, {"a.gpx": _ride(1)})
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("failed", "processing_failed")
        assert activities_of(committed_sessions, me.user.id) == []


class TestARefusedArchive:
    def test_one_with_nothing_importable_is_refused_before_a_job_exists(self, me, pool, committed_sessions, storage):
        response = _import(me, {"notes.txt": b"x"})

        assert response.status_code == 400
        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []
        assert not os.listdir(core_config.FILES_UPLOAD_INCOMING_DIR)
        assert _audit_rows(committed_sessions) == []

    def test_only_a_zip_is_accepted(self, me, pool, committed_sessions):
        response = me.client.post(_BULK, files={"file": ("ride.fit", fit_file())})

        assert response.status_code in (400, 415)
        assert all_jobs(committed_sessions) == []

    def test_an_unknown_source_is_refused(self, me, pool, committed_sessions):
        response = _import(me, {"a.gpx": _ride(1)}, source="polar")

        assert response.status_code == 400
        assert all_jobs(committed_sessions) == []

    def test_a_full_pool_refuses_it_before_anything_is_staged(self, me, committed_sessions, storage, monkeypatch):
        release = threading.Event()
        full = core_local_pool.BoundedPool("full", workers=1, max_pending=1)
        monkeypatch.setattr(ingestion_background, "_pool", full)
        full.submit(release.wait, 10)
        try:
            response = _import(me, {"a.gpx": _ride(1)})
        finally:
            release.set()
            full.shutdown(wait=True)

        assert response.status_code == 503
        assert all_jobs(committed_sessions) == []
        assert staged_keys(storage) == []


class TestASecondImport:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """The first import stays pending, so the second meets it."""

    def test_while_one_runs_is_a_conflict_that_names_the_running_job_and_is_audited_once(
        self, me, committed_sessions, storage
    ):
        first = _import(me, {"a.gpx": _ride(1)})

        second = _import(me, {"b.gpx": _ride(2)})

        assert second.status_code == 409
        assert second.headers["Content-Location"] == f"{_API}/jobs/{first.json()['id']}"
        assert second.json()["job_id"] == first.json()["id"]
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1
        assert len(_audit_rows(committed_sessions)) == 1

    def test_is_allowed_once_the_first_finished(self, me, committed_sessions):
        first = _import(me, {"a.gpx": _ride(1)})
        event = queued_events(committed_sessions)[0]
        _handler()(event)

        second = _import(me, {"b.gpx": _ride(2)})

        assert (first.status_code, second.status_code) == (202, 202)

    def test_the_database_decides_when_requests_race_the_check(self, me, committed_sessions, storage):
        barrier = threading.Barrier(4)
        responses: list = []

        def send(index: int) -> None:
            barrier.wait()
            responses.append(_import(me, {f"{index}.gpx": _ride(index)}))

        threads = [threading.Thread(target=send, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        statuses = sorted(response.status_code for response in responses)
        winner = next(response for response in responses if response.status_code == 202)
        assert statuses == [202, 409, 409, 409]
        assert all(
            response.json()["job_id"] == winner.json()["id"] for response in responses if response.status_code == 409
        )
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1, "the losers' staged archives did not stay behind"


class TestAnIdempotencyKey:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """Nothing runs the jobs, so a repeated request leaves a trace."""

    def test_is_stored_with_a_fingerprint_of_the_archive_and_its_source(self, me, committed_sessions):
        response = _import(me, {"a.gpx": _ride(1)}, key="k-1")

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert row.idempotency_key == "k-1"
        assert len(row.request_fingerprint) == 64

    def test_without_one_nothing_is_stored(self, me, committed_sessions):
        response = _import(me, {"a.gpx": _ride(1)})

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.idempotency_key, row.request_fingerprint) == (None, None)

    def test_a_replay_returns_the_original_job_without_staging_or_queueing_again(self, me, committed_sessions, storage):
        first = _import(me, {"a.gpx": _ride(1)}, key="k-2")
        replay = _import(me, {"a.gpx": _ride(1)}, key="k-2")

        assert replay.status_code == 202
        assert replay.json()["id"] == first.json()["id"]
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1
        assert len(queued_events(committed_sessions)) == 1

    def test_a_replay_of_a_finished_import_returns_it_in_its_current_state(self, me, committed_sessions):
        first = _import(me, {"a.gpx": _ride(1)}, key="k-3")
        _handler()(queued_events(committed_sessions)[0])

        replay = _import(me, {"a.gpx": _ride(1)}, key="k-3")

        assert replay.status_code == 202, replay.text
        assert replay.json()["id"] == first.json()["id"]
        assert replay.json()["status"] == "succeeded"

    def test_the_same_key_with_a_different_archive_is_refused(self, me, committed_sessions, storage):
        _import(me, {"a.gpx": _ride(1)}, key="k-4")

        reused = _import(me, {"a.gpx": _ride(2)}, key="k-4")

        assert reused.status_code == 422
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1

    def test_the_same_archive_read_as_another_source_is_another_request(self, me, committed_sessions, providers):
        ingestion_integration.register_bulk_import_format(
            _acme_format(lambda user_id, initiated, _read: _plain_source(user_id, initiated))
        )
        _import(me, {"a.gpx": _ride(1)}, key="k-5")

        other_source = _import(me, {"a.gpx": _ride(1)}, source="acme", key="k-5")

        assert other_source.status_code == 422

    def test_a_different_key_while_an_import_runs_is_still_a_conflict(self, me, committed_sessions):
        _import(me, {"a.gpx": _ride(1)}, key="k-6")

        assert _import(me, {"a.gpx": _ride(1)}, key="k-7").status_code == 409

    def test_is_scoped_to_bulk_imports(self, me, committed_sessions):
        upload = me.client.post(
            f"{_API}/activities/upload",
            files={"file": ("ride.gpx", _ride(1))},
            headers={"Idempotency-Key": '"k-8"'},
        )

        imported = _import(me, {"a.gpx": _ride(1)}, key="k-8")

        assert imported.status_code == 202
        assert imported.json()["id"] != upload.json()["id"]

    def test_requests_racing_with_one_key_return_the_winner(self, me, committed_sessions, storage):
        barrier = threading.Barrier(3)
        responses: list = []

        def send() -> None:
            barrier.wait()
            responses.append(_import(me, {"a.gpx": _ride(1)}, key="k-9"))

        threads = [threading.Thread(target=send) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert [response.status_code for response in responses] == [202] * 3
        assert len({response.json()["id"] for response in responses}) == 1
        assert len(all_jobs(committed_sessions)) == 1
        assert len(staged_keys(storage)) == 1


def _plain_source(user_id, initiated):
    return ingestion_contracts.BulkImportSource(import_initiated_time=initiated, user_id=user_id)


def _acme_format(build_source) -> ingestion_contracts.BulkImportFormat:
    return ingestion_contracts.BulkImportFormat(
        name="acme",
        is_activity_member=lambda name: name.startswith("activities/") and name.endswith(".gpx"),
        is_export_member=lambda name: True,
        drop_directory=lambda user_id: f"{core_config.FILES_BULK_IMPORT_DIR}/acme/{user_id}",
        build_source=build_source,
    )


class TestInBatches:
    """On the durable profile a batch stops at its budget, records its cursor and asks for the next one."""

    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """Every test here runs on the durable profile."""

    def _accept(self, me, members) -> uuid.UUID:
        return uuid.UUID(_import(me, members).json()["id"])

    def test_a_batch_stops_at_its_budget_and_asks_for_the_next_one(self, me, committed_sessions, storage, monkeypatch):
        monkeypatch.setattr(bulk, "_BATCH_MAX_FILES", 2)
        job_id = self._accept(me, {f"{name}.gpx": _ride(day) for day, name in enumerate("abcde", 1)})
        events_before = len(queued_events(committed_sessions))

        with pytest.raises(ContinueJob):
            _handler()(queued_events(committed_sessions)[0])

        row = read_job(committed_sessions, job_id)
        assert (row.status, row.files_done, row.cursor) == ("pending", 2, "b.gpx")
        assert len(queued_events(committed_sessions)) == events_before, "the same job runs the next batch"
        assert len(staged_keys(storage)) == 1

    def test_the_batches_import_each_file_once_in_order_and_the_last_one_finishes(
        self, me, committed_sessions, storage, monkeypatch
    ):
        monkeypatch.setattr(bulk, "_BATCH_MAX_FILES", 2)
        job_id = self._accept(me, {f"{name}.gpx": _ride(day) for day, name in enumerate("abcde", 1)})
        event = queued_events(committed_sessions)[0]

        results = []
        for _ in range(3):
            try:
                _handler()(event)
                results.append("finished")
            except ContinueJob:
                results.append("continue")

        row = read_job(committed_sessions, job_id)
        assert results == ["continue", "continue", "finished"]
        assert (row.status, row.files_done, row.files_failed) == ("completed", 5, 0)
        assert [activity.start_time for activity in activities_of(committed_sessions, me.user.id)] == sorted(
            activity.start_time for activity in activities_of(committed_sessions, me.user.id)
        )
        assert len(activities_of(committed_sessions, me.user.id)) == 5
        assert staged_keys(storage) == []

    def test_a_repeated_continuation_of_a_finished_import_does_nothing(self, me, committed_sessions):
        job_id = self._accept(me, {"a.gpx": _ride(1)})
        event = queued_events(committed_sessions)[0]
        _handler()(event)

        _handler()(event)

        assert len(activities_of(committed_sessions, me.user.id)) == 1
        assert read_job(committed_sessions, job_id).files_done == 1

    def test_a_member_stored_with_a_backslash_name_is_imported_under_its_normalised_name(self, me, committed_sessions):
        job_id = self._accept(me, {"a\\b.gpx": _ride(1), "c.gpx": _ride(2)})

        _handler()(queued_events(committed_sessions)[0])

        row = read_job(committed_sessions, job_id)
        assert (row.files_done, row.files_failed, row.cursor) == (2, 0, "c.gpx")

    def test_an_outage_is_left_for_the_retry_which_resumes_without_counting_a_file_twice(
        self, me, committed_sessions, storage
    ):
        job_id = self._accept(me, {"a.gpx": _ride(1), "b.gpx": _ride(2), "c.gpx": _ride(3)})
        down = FaultyStorage(storage, faults={"save": StorageBackendUnavailableError("storage is down")})

        with pytest.raises(StorageBackendUnavailableError):
            bulk.run_bulk_import_job(job_id, down)

        assert read_job(committed_sessions, job_id).status == "pending", "released for the retry to claim"
        assert bulk.run_bulk_import_job(job_id, storage) is False
        row = read_job(committed_sessions, job_id)
        assert (row.status, row.files_done, row.files_failed) == ("completed", 3, 0)
        assert len(activities_of(committed_sessions, me.user.id)) == 3

    def test_a_failed_file_that_cannot_be_kept_does_not_stop_the_batch(self, me, committed_sessions, storage, caplog):
        job_id = self._accept(me, {"a.gpx": EMPTY_GPX, "b.gpx": _ride(2)})

        class _KeepingFails(FaultyStorage):
            def __getattr__(self, name):
                if name == "save_stream":

                    def refuse(area, key, handle):
                        if area == _ERRORS:
                            raise StorageBackendUnavailableError("error area is down")
                        return self.inner.save_stream(area, key, handle)

                    return refuse
                return super().__getattr__(name)

        with caplog.at_level(logging.WARNING, logger=bulk.logger.name):
            bulk.run_bulk_import_job(job_id, _KeepingFails(storage))

        row = read_job(committed_sessions, job_id)
        assert (row.status, row.files_done, row.files_failed) == ("completed", 1, 1)
        assert any("could not keep a failed file" in record.getMessage() for record in caplog.records)

    def test_an_internal_failure_of_a_file_is_an_error_with_a_traceback_and_the_file_is_counted_failed(
        self, me, committed_sessions, storage, caplog
    ):
        job_id = self._accept(me, {"a.gpx": _ride(1)})
        broken = FaultyStorage(storage, faults={"save": OSError("disk full")})

        with caplog.at_level(logging.WARNING, logger=bulk.logger.name):
            bulk.run_bulk_import_job(job_id, broken)

        row = read_job(committed_sessions, job_id)
        assert (row.files_done, row.files_failed) == (0, 1)
        failure = next(record for record in caplog.records if "could not be imported" in record.getMessage())
        assert failure.levelno == logging.ERROR
        assert failure.exc_info is not None


class TestAProviderFormat:
    def _import(self, me, committed_sessions, members, build_source):
        ingestion_integration.register_bulk_import_format(_acme_format(build_source))
        return _import(me, members, source="acme")

    def test_only_the_formats_activity_members_are_imported_and_it_can_read_the_rest(
        self, me, providers, pool, committed_sessions
    ):
        read: dict[str, bytes | None] = {}

        def build_source(user_id, initiated, read_member):
            read["manifest"] = read_member("manifest.csv")
            read["missing"] = read_member("nope")
            return _plain_source(user_id, initiated)

        response = self._import(
            me,
            committed_sessions,
            {"manifest.csv": b"m", "activities/a.gpx": _ride(1), "media/p.jpg": b"2", "b.gpx": _ride(2)},
            build_source,
        )
        pool.drain()

        assert response.json()["files_total"] == 1
        assert len(activities_of(committed_sessions, me.user.id)) == 1
        assert read == {"manifest": b"m", "missing": None}

    def test_an_archive_that_is_not_a_valid_export_fails_the_job_with_a_specific_code(
        self, me, providers, pool, committed_sessions, storage
    ):
        def build_source(*_args):
            raise core_exceptions.InvalidInputError("The export has no manifest")

        response = self._import(me, committed_sessions, {"activities/a.gpx": _ride(1)}, build_source)
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code, row.staged_key) == ("failed", "invalid_file", None)
        assert activities_of(committed_sessions, me.user.id) == []
        assert staged_keys(storage) == []


class TestAFolderImport:
    def test_is_packed_staged_imported_and_only_then_consumed(self, me, pool, committed_sessions):
        folder = _drop_folder(me.user.id, {"a.gpx": _ride(1), "sub/b.gpx": _ride(2), "notes.txt": b"n"})

        response = me.client.post(f"{_BULK}/folder")
        pool.drain()

        assert response.status_code == 202, response.text
        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_done, row.files_total) == ("completed", 2, 2)
        assert len(activities_of(committed_sessions, me.user.id)) == 2
        assert not (folder / "a.gpx").exists()
        assert not (folder / "sub" / "b.gpx").exists()
        assert (folder / "notes.txt").exists(), "what is not part of the export is left where it was"

    def test_is_audited_without_a_count_or_a_path(self, me, pool, committed_sessions):
        _drop_folder(me.user.id, {"a.gpx": _ride(1)})

        response = me.client.post(f"{_BULK}/folder")
        pool.drain()

        (entry,) = _audit_rows(committed_sessions)
        assert entry.target_id == response.json()["id"]
        assert entry.details == {"source": "server_directory", "file_count": None}

    def test_an_empty_folder_is_refused_before_a_job_exists_and_is_not_audited(self, me, pool, committed_sessions):
        response = me.client.post(f"{_BULK}/folder")

        assert response.status_code == 400
        assert all_jobs(committed_sessions) == []
        assert _audit_rows(committed_sessions) == []

    def test_another_users_folder_is_neither_imported_nor_consumed(self, me, make_signed_in, pool, committed_sessions):
        other = make_signed_in()
        mine = _drop_folder(me.user.id, {"mine.gpx": _ride(1)})
        theirs = _drop_folder(other.user.id, {"theirs.gpx": _ride(2)})

        me.client.post(f"{_BULK}/folder")
        pool.drain()

        assert len(activities_of(committed_sessions, me.user.id)) == 1
        assert activities_of(committed_sessions, other.user.id) == []
        assert not (mine / "mine.gpx").exists()
        assert (theirs / "theirs.gpx").exists()

    def test_a_symlink_in_the_folder_is_not_packed(self, me, pool, committed_sessions, tmp_path):
        secret = tmp_path / "secret.gpx"
        secret.write_bytes(_ride(5))
        folder = _drop_folder(me.user.id, {"a.gpx": _ride(1)})
        os.symlink(secret, folder / "link.gpx")

        me.client.post(f"{_BULK}/folder")
        pool.drain()

        assert len(activities_of(committed_sessions, me.user.id)) == 1
        assert secret.exists()

    def test_a_failure_staging_leaves_the_users_files_where_they_were(
        self, me, pool, committed_sessions, break_storage
    ):
        folder = _drop_folder(me.user.id, {"a.gpx": _ride(1)})
        break_storage(save_stream=OSError("bucket down"))

        response = me.client.post(f"{_BULK}/folder")
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("failed", "processing_failed")
        assert (folder / "a.gpx").exists()

    def test_a_second_import_while_one_is_running_is_a_conflict(self, me, committed_sessions):
        _drop_folder(me.user.id, {"a.gpx": _ride(1)})
        with committed_sessions() as db:
            running = stage_job(db, me.user.id, kind=_Kind.BULK_IMPORT, status="processing", import_source="generic")
            db.commit()

        response = me.client.post(f"{_BULK}/folder")

        assert response.status_code == 409
        assert response.json()["job_id"] == str(running.id)


def _beat_warnings(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if "Could not touch a bulk import" in record.getMessage()]


class TestALostFolderPack:
    """A folder import whose packing was lost mid-way frees the user's slot soon, not after a day."""

    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """Nothing runs the jobs inline."""

    def _folder_job(self, me, committed_sessions, *, idle_minutes: int) -> tuple[uuid.UUID, Path]:
        folder = _drop_folder(me.user.id, {"a.gpx": _ride(1)})
        with committed_sessions() as db:
            job = stage_job(
                db,
                me.user.id,
                kind=_Kind.BULK_IMPORT,
                import_source="generic",
                updated_at=datetime.now(UTC) - timedelta(minutes=idle_minutes),
            )
            db.commit()
        return job.id, folder

    def _reap(self, platform, storage) -> None:
        ingestion_service.fail_stale_ingestion_jobs(platform.clock, storage)

    def test_a_pack_that_stopped_beating_is_failed_so_the_user_can_import_again(
        self, me, committed_sessions, platform, storage
    ):
        job_id, _folder = self._folder_job(me, committed_sessions, idle_minutes=60)

        self._reap(platform, storage)

        assert read_job(committed_sessions, job_id).status == "failed"
        with committed_sessions() as db:
            assert ingestion_service.activity_ingestion_crud.get_active_bulk_import_job_id(me.user.id, db) is None

    def test_a_pack_that_is_still_beating_is_left_running(self, me, committed_sessions, platform, storage):
        job_id, _folder = self._folder_job(me, committed_sessions, idle_minutes=1)

        self._reap(platform, storage)

        assert read_job(committed_sessions, job_id).status == "pending"

    def test_a_staged_import_waiting_in_the_queue_is_not_failed_early(self, me, committed_sessions, platform, storage):
        response = _import(me, {"a.gpx": _ride(1)})
        job_id = uuid.UUID(response.json()["id"])
        with committed_sessions() as db:
            db.execute(
                update(ingestion_models.ActivityIngestionJob)
                .where(ingestion_models.ActivityIngestionJob.id == job_id)
                .values(updated_at=datetime.now(UTC) - timedelta(hours=2))
            )
            db.commit()

        self._reap(platform, storage)

        assert read_job(committed_sessions, job_id).status == "pending"

    def test_packing_keeps_the_job_beating(self, me, committed_sessions, monkeypatch):
        job_id, _folder = self._folder_job(me, committed_sessions, idle_minutes=60)
        before = read_job(committed_sessions, job_id).updated_at
        monkeypatch.setattr(bulk, "_HEARTBEAT_SECONDS", 0.01)
        pause = threading.Event()
        deadline = datetime.now(UTC) + timedelta(seconds=10)

        with bulk._heartbeat(job_id):
            while read_job(committed_sessions, job_id).updated_at == before and datetime.now(UTC) < deadline:
                pause.wait(0.02)

        assert read_job(committed_sessions, job_id).updated_at != before

    def test_a_beat_the_database_refuses_is_logged_and_the_beat_goes_on(self, monkeypatch, caplog):
        monkeypatch.setattr(bulk, "_HEARTBEAT_SECONDS", 0.01)
        pause = threading.Event()
        not_a_job = cast(uuid.UUID, "not-a-job-id")

        with caplog.at_level(logging.WARNING, logger=bulk.logger.name), bulk._heartbeat(not_a_job):
            deadline = datetime.now(UTC) + timedelta(seconds=10)
            while len(_beat_warnings(caplog)) < 2 and datetime.now(UTC) < deadline:
                pause.wait(0.02)

        assert len(_beat_warnings(caplog)) >= 2

    def test_a_pack_finishing_after_the_job_was_failed_neither_imports_nor_consumes_the_files(
        self, me, committed_sessions, platform, storage
    ):
        job_id, folder = self._folder_job(me, committed_sessions, idle_minutes=60)
        self._reap(platform, storage)

        bulk.feed_archive_from_directory(job_id, me.user.id, "generic", str(folder), storage)

        assert (folder / "a.gpx").exists()
        assert activities_of(committed_sessions, me.user.id) == []
        assert read_job(committed_sessions, job_id).status == "failed"
        assert staged_keys(storage) == []

    def test_a_folder_the_user_filled_wrongly_is_a_warning_and_a_staging_failure_an_error(
        self, me, committed_sessions, storage, caplog
    ):
        job_id, folder = self._folder_job(me, committed_sessions, idle_minutes=1)

        with caplog.at_level(logging.WARNING, logger=bulk.logger.name):
            bulk.feed_archive_from_directory(
                job_id,
                me.user.id,
                "generic",
                str(folder),
                FaultyStorage(storage, faults={"save_stream": OSError("disk full")}),
            )

        failure = next(record for record in caplog.records if "Could not stage" in record.getMessage())
        assert failure.levelno == logging.ERROR
        assert read_job(committed_sessions, job_id).status == "failed"


class TestWhatTheGenericFormatImports:
    def test_operating_system_metadata_is_not_an_activity(self, me, pool, committed_sessions):
        response = _import(me, {"a.gpx": _ride(1), "__MACOSX/._a.gpx": b"meta", ".hidden.gpx": _ride(2)})
        pool.drain()

        assert response.json()["files_total"] == 1
        assert len(activities_of(committed_sessions, me.user.id)) == 1

    def test_progress_is_saved_along_the_way_and_every_file_is_counted(self, me, pool, committed_sessions):
        members = {f"{day:02d}.gpx": _ride(day) for day in range(1, 12)}

        response = _import(me, members)
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_done, row.files_total) == ("completed", 11, 11)
        assert len(activities_of(committed_sessions, me.user.id)) == 11


class TestASourceThatSkipsDuplicates:
    def test_an_activity_the_source_does_not_want_is_counted_done_but_not_stored(
        self, me, providers, pool, committed_sessions
    ):
        class _SkipsAll(ingestion_contracts.BulkImportSource):
            def should_import(self, activity, activity_metadata, *, activities_in_file):
                return False

        ingestion_integration.register_bulk_import_format(
            _acme_format(lambda user_id, initiated, _read: _SkipsAll(import_initiated_time=initiated, user_id=user_id))
        )

        response = _import(me, {"activities/a.gpx": _ride(1)}, source="acme")
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_done, row.files_failed) == ("completed", 1, 0)
        assert activities_of(committed_sessions, me.user.id) == []


class TestAFormatThatReadsTooMuch:
    def test_a_member_over_the_read_limit_fails_the_import_instead_of_exhausting_memory(
        self, me, providers, pool, committed_sessions, monkeypatch
    ):
        monkeypatch.setattr(bulk.core_file_uploads, "MAX_READ_MEMBER_BYTES", 10)

        def build_source(user_id, initiated, read_member):
            read_member("manifest.csv")
            return _plain_source(user_id, initiated)

        ingestion_integration.register_bulk_import_format(_acme_format(build_source))

        response = _import(me, {"manifest.csv": b"x" * 100, "activities/a.gpx": _ride(1)}, source="acme")
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.error_code) == ("failed", "processing_failed")
        assert activities_of(committed_sessions, me.user.id) == []


class TestRunningAJobThatCannotRun:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """A worker runs these, as the handler does."""

    def test_a_folder_job_still_being_packed_is_left_for_when_its_archive_is_staged(
        self, me, committed_sessions, storage
    ):
        with committed_sessions() as db:
            packing = stage_job(db, me.user.id, kind=_Kind.BULK_IMPORT, import_source="generic")
            db.commit()

        assert bulk.run_bulk_import_job(packing.id, storage) is False
        assert read_job(committed_sessions, packing.id).status == "pending"

    def test_a_batch_another_worker_holds_is_not_run_twice(self, me, committed_sessions, storage):
        with committed_sessions() as db:
            held = stage_job(
                db,
                me.user.id,
                kind=_Kind.BULK_IMPORT,
                status="processing",
                staged_key="bulk-x.zip",
                import_source="generic",
                files_total=1,
            )
            db.commit()

        assert bulk.run_bulk_import_job(held.id, storage) is False
        assert read_job(committed_sessions, held.id).status == "processing"

    def test_a_format_this_process_does_not_know_fails_the_job_and_drops_its_archive(
        self, me, providers, committed_sessions, storage
    ):
        key = f"bulk-{uuid.uuid4()}.zip"
        stage_blob(storage, key, archive_of({"a.gpx": _ride(1)}))
        with committed_sessions() as db:
            job = stage_job(
                db, me.user.id, kind=_Kind.BULK_IMPORT, staged_key=key, import_source="ghost", files_total=1
            )
            db.commit()

        assert bulk.run_bulk_import_job(job.id, storage) is False

        row = read_job(committed_sessions, job.id)
        assert (row.status, row.error_code) == ("failed", "processing_failed")
        assert staged_keys(storage) == []

    def test_an_archive_that_is_gone_fails_the_job_as_an_invalid_file(self, me, committed_sessions, storage):
        with committed_sessions() as db:
            job = stage_job(
                db,
                me.user.id,
                kind=_Kind.BULK_IMPORT,
                staged_key="bulk-missing.zip",
                import_source="generic",
                files_total=1,
            )
            db.commit()

        assert bulk.run_bulk_import_job(job.id, storage) is False

        row = read_job(committed_sessions, job.id)
        assert (row.status, row.error_code) == ("failed", "invalid_file")


class TestAFolderImportOnTheDurableProfile:
    @pytest.fixture(autouse=True)
    def _durable(self, durable_jobs):
        """A worker imports the staged archive."""

    def test_is_packed_and_staged_on_this_node_and_the_import_is_left_to_a_worker(
        self, me, pool, committed_sessions, storage
    ):
        folder = _drop_folder(me.user.id, {"a.gpx": _ride(1), "b.gpx": _ride(2)})

        response = me.client.post(f"{_BULK}/folder")
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_total, len(staged_keys(storage))) == ("pending", 2, 1)
        assert not (folder / "a.gpx").exists()
        (event,) = queued_events(committed_sessions)
        assert event.payload["job_id"] == response.json()["id"]
        assert activities_of(committed_sessions, me.user.id) == []

    def test_the_worker_then_imports_what_was_staged(self, me, pool, committed_sessions):
        _drop_folder(me.user.id, {"a.gpx": _ride(1)})
        me.client.post(f"{_BULK}/folder")
        pool.drain()

        _handler()(queued_events(committed_sessions)[0])

        assert len(activities_of(committed_sessions, me.user.id)) == 1


class TestAFolderOfAProviderExport:
    def test_packs_the_exports_media_but_counts_only_its_activity_files(self, me, providers, pool, committed_sessions):
        ingestion_integration.register_bulk_import_format(
            ingestion_contracts.BulkImportFormat(
                name="acme",
                is_activity_member=lambda name: name.startswith("activities/") and name.endswith(".gpx"),
                is_export_member=lambda name: not name.startswith("ignored/"),
                drop_directory=lambda user_id: core_config.bulk_import_dir_for(user_id),
                build_source=lambda user_id, initiated, _read: _plain_source(user_id, initiated),
            )
        )
        folder = _drop_folder(
            me.user.id, {"activities/a.gpx": _ride(1), "media/photo.jpg": b"jpg", "ignored/other.txt": b"keep"}
        )

        response = me.client.post(f"{_BULK}/folder", params={"source": "acme"})
        pool.drain()

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_total, row.files_done) == ("completed", 1, 1)
        assert not (folder / "media" / "photo.jpg").exists(), "the export's media travelled with the archive"
        assert (folder / "ignored" / "other.txt").exists()


class TestAFolderImportThatCannotConsumeItsFiles:
    def test_a_file_that_cannot_be_removed_is_a_warning_and_the_import_still_completes(
        self, me, pool, committed_sessions, caplog
    ):
        folder = _drop_folder(me.user.id, {"sub/a.gpx": _ride(1)})
        os.chmod(folder / "sub", stat.S_IRUSR | stat.S_IXUSR)
        try:
            with caplog.at_level(logging.WARNING, logger=bulk.logger.name):
                response = me.client.post(f"{_BULK}/folder")
                pool.drain()
        finally:
            os.chmod(folder / "sub", stat.S_IRWXU)

        row = read_job(committed_sessions, uuid.UUID(response.json()["id"]))
        assert (row.status, row.files_done) == ("completed", 1)
        assert (folder / "sub" / "a.gpx").exists()
        assert any("could not remove the original" in record.getMessage() for record in caplog.records)


class TestFolderImportsRacing:
    def test_only_one_runs_and_the_others_are_told_which(self, me, pool, committed_sessions):
        _drop_folder(me.user.id, {"a.gpx": _ride(1)})
        barrier = threading.Barrier(4)
        responses: list = []

        def send() -> None:
            barrier.wait()
            responses.append(me.client.post(f"{_BULK}/folder"))

        threads = [threading.Thread(target=send) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        pool.drain()

        accepted = [response for response in responses if response.status_code == 202]
        assert len(accepted) == 1
        assert sorted(response.status_code for response in responses) == [202, 409, 409, 409]
        assert len(all_jobs(committed_sessions)) == 1
