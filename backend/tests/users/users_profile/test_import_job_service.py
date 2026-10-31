"""Tests for users_profile.import_job_service: accepting, running and sweeping profile imports."""

import os
import time
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.exc import OperationalError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.import_job_service as job_service
import modules.users.users_profile.import_state_store as import_state_store

_MODULE = "modules.users.users_profile.import_job_service"
_Status = profile_constants.ImportStatus
_Failure = profile_constants.ImportFailure
_AREA = profile_constants.IMPORT_STAGING_AREA


@pytest.fixture
def states():
    return import_state_store.ProfileImportStateStore(MemoryState())


@pytest.fixture
def storage():
    store = MagicMock()
    store.get.return_value = b"zip"
    return store


def _saver(data: bytes = b"zip"):
    """An upload saver that writes ``data`` where the shared validator would."""

    def save(*, kind, upload_dir, filename):
        path = os.path.join(upload_dir, filename)
        with open(path, "wb") as out:
            out.write(data)
        return path

    return save


def _validation_error() -> ValidationError:
    try:
        TypeAdapter(int).validate_python("x")
    except ValidationError as err:
        return err
    raise AssertionError


def _payload(user_id: int = 1, key: str | None = None) -> profile_events.ProfileImportRequestedPayload:
    return profile_events.ProfileImportRequestedPayload(user_id=user_id, staged_key=key or f"{user_id}/abc.zip")


def _queued(states, user_id: int = 1) -> None:
    states.begin(user_id)


def _run(states, storage, importer, *, will_retry=False, payload=None):
    with patch(f"{_MODULE}._run_importer", side_effect=importer if isinstance(importer, Exception) else None) as run:
        if not isinstance(importer, Exception):
            run.return_value = importer
        job_service.run_import(payload or _payload(), states, storage, will_retry=will_retry)
    return run


class TestRequestImport:
    def test_a_full_local_pool_refuses_before_anything_is_staged(self, states, storage, mock_db):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_MODULE}.profile_transfer_pool.pool") as pool,
        ):
            pool.require_capacity.side_effect = core_exceptions.ServiceUnavailableError("full")
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                job_service.request_import(7, _saver(), states, storage, mock_db)

        storage.save_stream.assert_not_called()
        assert states.get(7) is None

    def test_a_durable_deployment_does_not_look_at_the_local_pool(self, states, storage, mock_db):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=True)),
            patch(f"{_MODULE}.profile_transfer_pool.pool") as pool,
            patch(f"{_MODULE}.profile_event_publishers.publish_import_requested"),
        ):
            job_service.request_import(7, _saver(), states, storage, mock_db)

        pool.require_capacity.assert_not_called()

    def test_an_import_the_pool_could_not_take_is_closed_and_its_archive_removed(self, states, storage):
        _queued(states, 7)

        job_service.fail_unstarted_import(_payload(7), states, storage)

        assert states.get(7).status == _Status.FAILED
        assert states.get(7).failure == _Failure.PROCESSING_FAILED
        storage.delete.assert_called_once_with(_AREA, "7/abc.zip")

    def test_stages_the_archive_under_the_users_prefix_and_queues_it(self, states, storage, mock_db):
        with patch(f"{_MODULE}.profile_event_publishers.publish_import_requested") as publish:
            state = job_service.request_import(7, _saver(), states, storage, mock_db)

        assert state.status == _Status.QUEUED
        area, key = storage.save_stream.call_args.args[:2]
        assert area == _AREA
        assert key.startswith("7/") and key.endswith(".zip")
        publish.assert_called_once_with(7, key, mock_db, commit=mock_db.commit)
        assert states.get(7).status == _Status.QUEUED

    def test_a_pending_import_refuses_a_second_and_stages_nothing(self, states, storage, mock_db):
        states.begin(7)

        saver = MagicMock()
        with pytest.raises(core_exceptions.ConflictError):
            job_service.request_import(7, saver, states, storage, mock_db)

        saver.assert_not_called()
        storage.save_stream.assert_not_called()

    def test_the_archive_is_streamed_from_disk_never_read_into_memory(self, states, storage, mock_db):
        streamed = []
        storage.save_stream.side_effect = lambda area, key, source, **_: streamed.append(source.read())

        with patch(f"{_MODULE}.profile_event_publishers.publish_import_requested"):
            job_service.request_import(7, _saver(b"archive-bytes"), states, storage, mock_db)

        assert streamed == [b"archive-bytes"]

    def test_a_rejected_archive_frees_the_claim_and_records_no_import(self, states, storage, mock_db):
        saver = MagicMock(side_effect=core_exceptions.InvalidInputError("not a zip"))

        with pytest.raises(core_exceptions.InvalidInputError):
            job_service.request_import(7, saver, states, storage, mock_db)

        storage.save_stream.assert_not_called()
        storage.delete.assert_not_called()
        assert states.get(7) is None
        assert states.begin(7) is True

    def test_a_failure_to_queue_removes_the_archive_and_closes_the_state(self, states, storage, mock_db):
        with (
            patch(f"{_MODULE}.profile_event_publishers.publish_import_requested", side_effect=RuntimeError("down")),
            pytest.raises(RuntimeError),
        ):
            job_service.request_import(7, _saver(), states, storage, mock_db)

        storage.delete.assert_called_once()
        assert states.get(7).status == _Status.FAILED
        assert states.begin(7) is True


class TestGetImportStatus:
    def test_returns_the_state(self, states):
        states.begin(1)

        assert job_service.get_import_status(1, states).status == _Status.QUEUED

    def test_unknown_is_not_found(self, states):
        with pytest.raises(core_exceptions.NotFoundError):
            job_service.get_import_status(1, states)


class TestRunImport:
    def test_a_successful_import_records_the_counts_and_removes_the_archive(self, states, storage):
        _queued(states)

        _run(states, storage, {"activities": 3})

        state = states.get(1)
        assert (state.status, state.imported) == (_Status.COMPLETED, {"activities": 3})
        storage.delete.assert_called_once_with(_AREA, "1/abc.zip")
        assert states.begin(1) is True

    def test_it_reads_the_archive_the_event_names(self, states, storage):
        _queued(states)

        run = _run(states, storage, {})

        storage.get.assert_called_once_with(_AREA, "1/abc.zip")
        assert run.call_args.args[:2] == (1, b"zip")

    def test_an_archive_outside_the_users_prefix_is_refused(self, states, storage):
        _queued(states)

        run = _run(states, storage, {}, payload=_payload(1, "2/abc.zip"))

        run.assert_not_called()
        storage.get.assert_not_called()
        assert states.get(1).status == _Status.QUEUED

    @pytest.mark.parametrize(
        ("error", "failure"),
        [
            (profile_exceptions.FileFormatError("x"), _Failure.INVALID_FILE),
            (profile_exceptions.SchemaValidationError("x"), _Failure.INVALID_FILE),
            (_validation_error(), _Failure.INVALID_FILE),
            (ValueError("x"), _Failure.PROCESSING_FAILED),
            (core_exceptions.InvalidInputError("x"), _Failure.INVALID_FILE),
            (profile_exceptions.FileSizeError("x"), _Failure.TOO_LARGE),
            (profile_exceptions.ActivityLimitError("x"), _Failure.TOO_MANY_ACTIVITIES),
            (profile_exceptions.ImportTimeoutError("x"), _Failure.TIMED_OUT),
            (profile_exceptions.MemoryAllocationError("x"), _Failure.PROCESSING_FAILED),
            (RuntimeError("x"), _Failure.PROCESSING_FAILED),
        ],
    )
    def test_a_failure_is_final_and_reported_with_a_sanitized_code(self, states, storage, error, failure):
        _queued(states)

        _run(states, storage, error, will_retry=False)

        state = states.get(1)
        assert (state.status, state.failure) == (_Status.FAILED, failure)
        storage.delete.assert_called_once()
        assert "x" not in state.model_dump_json().replace("failure", "")

    def test_a_transient_failure_before_the_commit_is_retried(self, states, storage):
        _queued(states)

        with pytest.raises(OperationalError):
            _run(states, storage, OperationalError("s", {}, Exception("db down")), will_retry=True)

        assert states.get(1).status == _Status.QUEUED
        storage.delete.assert_not_called()

    def test_a_transient_failure_on_the_last_attempt_is_final(self, states, storage):
        _queued(states)

        _run(states, storage, OperationalError("s", {}, Exception("db down")), will_retry=False)

        assert states.get(1).status == _Status.FAILED
        storage.delete.assert_called_once()

    def test_a_rejected_archive_is_never_retried(self, states, storage):
        _queued(states)

        _run(states, storage, profile_exceptions.FileFormatError("x"), will_retry=True)

        assert states.get(1).failure == _Failure.INVALID_FILE

    def test_a_failure_after_the_commit_is_final_and_says_files_are_incomplete(self, states, storage):
        _queued(states)

        def commit_then_fail(_user_id, _zip, _storage, on_committed):
            on_committed()
            raise OperationalError("s", {}, Exception("storage down"))

        with patch(f"{_MODULE}._run_importer", side_effect=commit_then_fail):
            job_service.run_import(_payload(), states, storage, will_retry=True)

        assert (states.get(1).status, states.get(1).failure) == (_Status.FAILED, _Failure.FILES_INCOMPLETE)

    def test_losing_the_committed_marker_fails_the_import_instead_of_retrying_it(self, states, storage):
        _queued(states)

        def commit_with_state_down(_user_id, _zip, _storage, on_committed):
            with patch.object(states, "set_status", side_effect=core_attempt_state.StateUnavailableError("down")):
                on_committed()

        with patch(f"{_MODULE}._run_importer", side_effect=commit_with_state_down):
            job_service.run_import(_payload(), states, storage, will_retry=True)

        assert (states.get(1).status, states.get(1).failure) == (_Status.FAILED, _Failure.FILES_INCOMPLETE)

    def test_a_redelivery_after_a_worker_died_in_the_database_part_runs_again(self, states, storage):
        _queued(states)
        states.set_status(1, _Status.RUNNING)

        run = _run(states, storage, {"gears": 1})

        run.assert_called_once()
        assert states.get(1).status == _Status.COMPLETED

    def test_a_redelivery_after_a_worker_died_writing_files_does_not_import_twice(self, states, storage):
        _queued(states)
        states.set_status(1, _Status.WRITING_FILES)

        run = _run(states, storage, {})

        run.assert_not_called()
        assert (states.get(1).status, states.get(1).failure) == (_Status.FAILED, _Failure.FILES_INCOMPLETE)
        storage.delete.assert_called_once()

    @pytest.mark.parametrize("finished", [_Status.COMPLETED, _Status.FAILED])
    def test_a_redelivery_of_a_finished_import_does_nothing(self, states, storage, finished):
        _queued(states)
        states.set_status(1, finished)

        run = _run(states, storage, {})

        run.assert_not_called()
        assert states.get(1).status == finished

    def test_a_missing_archive_fails_the_import(self, states, storage):
        _queued(states)
        storage.get.return_value = None

        run = _run(states, storage, {})

        run.assert_not_called()
        assert states.get(1).status == _Status.FAILED


class TestRunImporter:
    def test_it_flips_the_state_once_the_rows_are_committed(self, states, storage):
        _queued(states)
        seen = []

        class FakeImporter:
            def __init__(self, user_id, store, db, on_database_committed):
                self.on_database_committed = on_database_committed

            async def import_from_zip_data(self, data):
                self.on_database_committed()
                seen.append(states.get(1).status)
                return {"imported": {"gears": 2}}

        with (
            patch(f"{_MODULE}.core_database.SessionLocal"),
            patch(f"{_MODULE}.profile_import_service.ImportService", FakeImporter),
        ):
            result = job_service._run_importer(1, b"zip", storage, lambda: states.set_status(1, _Status.WRITING_FILES))

        assert result == {"gears": 2}
        assert seen == [_Status.WRITING_FILES]


class TestSweepStagedImports:
    def test_removes_only_archives_older_than_the_cutoff(self, storage):
        now = time.time()
        storage.iter_objects.return_value = iter([("1/old.zip", now - 100_000), ("2/new.zip", now - 10)])

        removed = job_service.sweep_staged_imports(storage, 3600)

        assert removed == 1
        storage.delete.assert_called_once_with(_AREA, "1/old.zip")

    def test_nothing_stale_removes_nothing(self, storage):
        storage.iter_objects.return_value = iter([])

        assert job_service.sweep_staged_imports(storage, 3600) == 0
        storage.delete.assert_not_called()


class TestSweepSurvivesAFailedDelete:
    def test_one_failing_delete_does_not_stop_the_rest(self, storage):
        now = time.time()
        storage.iter_objects.return_value = iter([("1/a.zip", now - 100_000), ("2/b.zip", now - 100_000)])
        storage.delete.side_effect = [OSError("busy"), None]

        removed = job_service.sweep_staged_imports(storage, 3600)

        assert removed == 1
        assert storage.delete.call_count == 2


class TestDiscardStagedImports:
    def test_removes_every_archive_of_the_user(self, storage):
        storage.list_keys.return_value = ["7/a.zip", "7/b.zip"]

        job_service.discard_staged_imports(7, storage)

        storage.list_keys.assert_called_once_with(_AREA, "7/")
        assert [c.args for c in storage.delete.call_args_list] == [(_AREA, "7/a.zip"), (_AREA, "7/b.zip")]

    def test_a_storage_failure_is_logged_not_raised(self, storage):
        storage.list_keys.side_effect = OSError("down")

        job_service.discard_staged_imports(7, storage)


class TestCloseDeadLetteredImport:
    @pytest.mark.parametrize(
        ("status", "failure"),
        [
            (_Status.QUEUED, _Failure.PROCESSING_FAILED),
            (_Status.RUNNING, _Failure.PROCESSING_FAILED),
            (_Status.WRITING_FILES, _Failure.FILES_INCOMPLETE),
        ],
    )
    def test_a_pending_import_is_failed_with_the_reason_its_state_implies(self, states, storage, status, failure):
        states.begin(1)
        states.set_status(1, status)

        job_service.close_dead_lettered_import(_payload(1), states, storage)

        assert states.get(1).status == _Status.FAILED
        assert states.get(1).failure == failure
        assert states.begin(1) is True

    def test_the_staged_archive_is_always_removed(self, states, storage):
        job_service.close_dead_lettered_import(_payload(1), states, storage)

        storage.delete.assert_called_once_with(_AREA, "1/abc.zip")

    def test_an_import_that_already_finished_keeps_its_outcome(self, states, storage):
        states.begin(1)
        states.set_status(1, _Status.COMPLETED)

        job_service.close_dead_lettered_import(_payload(1), states, storage)

        assert states.get(1).status == _Status.COMPLETED
