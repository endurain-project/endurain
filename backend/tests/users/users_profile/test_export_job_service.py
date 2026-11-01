"""Tests for users_profile.export_job_service: accepting, running, serving and sweeping profile exports."""

import io
import time
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.export_job_service as job_service
import modules.users.users_profile.export_state_store as export_state_store

_MODULE = "modules.users.users_profile.export_job_service"
_Status = profile_constants.ExportStatus
_Failure = profile_constants.ExportFailure
_AREA = profile_constants.EXPORT_STAGING_AREA


@pytest.fixture
def states():
    return export_state_store.ProfileExportStateStore(MemoryState())


def _payload(user_id: int = 1) -> profile_events.ProfileExportRequestedPayload:
    return profile_events.ProfileExportRequestedPayload(user_id=user_id)


def _run(states, outcome, *, will_retry=False):
    stage = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
    with (
        patch(f"{_MODULE}.core_database.SessionLocal"),
        patch(f"{_MODULE}.profile_service.stage_export", **stage) as stage_export,
    ):
        job_service.run_export(_payload(), states, MagicMock(), will_retry=will_retry)
    return stage_export


class TestRequestExport:
    def test_a_full_local_pool_refuses_before_the_claim_is_taken(self, states, mock_db):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_MODULE}.profile_transfer_pool.pool") as pool,
        ):
            pool.require_capacity.side_effect = core_exceptions.ServiceUnavailableError("full")
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                job_service.request_export(7, states, mock_db)

        assert states.get(7) is None

    def test_a_durable_deployment_does_not_look_at_the_local_pool(self, states, mock_db):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=True)),
            patch(f"{_MODULE}.profile_transfer_pool.pool") as pool,
            patch(f"{_MODULE}.profile_event_publishers.publish_export_requested"),
        ):
            job_service.request_export(7, states, mock_db)

        pool.require_capacity.assert_not_called()

    def test_an_export_the_pool_could_not_take_is_closed(self, states):
        states.begin(7)

        job_service.fail_unstarted_export(_payload(7), states)

        assert states.get(7).status == _Status.FAILED
        assert states.get(7).failure == _Failure.PROCESSING_FAILED

    def test_queues_the_export(self, states, mock_db):
        with patch(f"{_MODULE}.profile_event_publishers.publish_export_requested") as publish:
            state = job_service.request_export(7, states, mock_db)

        assert state.status == _Status.QUEUED
        publish.assert_called_once_with(7, mock_db, commit=mock_db.commit)

    def test_a_pending_export_refuses_a_second(self, states, mock_db):
        states.begin(7)

        with pytest.raises(core_exceptions.ConflictError):
            job_service.request_export(7, states, mock_db)

    def test_a_failure_to_queue_closes_the_state_and_frees_the_claim(self, states, mock_db):
        with (
            patch(f"{_MODULE}.profile_event_publishers.publish_export_requested", side_effect=RuntimeError("down")),
            pytest.raises(RuntimeError),
        ):
            job_service.request_export(7, states, mock_db)

        assert states.get(7).status == _Status.FAILED
        assert states.begin(7) is True


class TestRunExport:
    def test_a_finished_export_records_its_size(self, states):
        states.begin(1)

        _run(states, 42)

        state = states.get(1)
        assert (state.status, state.size_bytes) == (_Status.COMPLETED, 42)
        assert states.begin(1) is True

    @pytest.mark.parametrize("finished", [_Status.COMPLETED, _Status.FAILED])
    def test_a_redelivery_of_a_finished_export_does_nothing(self, states, finished):
        states.begin(1)
        states.set_status(1, finished)

        stage = _run(states, 1)

        stage.assert_not_called()

    def test_a_redelivery_after_a_worker_died_builds_again(self, states):
        states.begin(1)
        states.set_status(1, _Status.RUNNING)

        stage = _run(states, 5)

        stage.assert_called_once()
        assert states.get(1).status == _Status.COMPLETED

    def test_a_transient_failure_is_retried(self, states):
        states.begin(1)

        with pytest.raises(OperationalError):
            _run(states, OperationalError("s", {}, Exception("db down")), will_retry=True)

        assert states.get(1).status == _Status.QUEUED

    def test_a_database_failure_wrapped_by_the_collection_is_retried(self, states):
        states.begin(1)
        try:
            raise OperationalError("s", {}, Exception("db down"))
        except OperationalError as db_err:
            wrapped = profile_exceptions.TransferUnprocessableError("Data collection failed")
            wrapped.__cause__ = db_err

        with pytest.raises(profile_exceptions.TransferUnprocessableError):
            _run(states, wrapped, will_retry=True)

        assert states.get(1).status == _Status.QUEUED

    def test_a_transient_failure_on_the_last_attempt_is_final(self, states):
        states.begin(1)

        _run(states, OperationalError("s", {}, Exception("db down")), will_retry=False)

        assert (states.get(1).status, states.get(1).failure) == (_Status.FAILED, _Failure.PROCESSING_FAILED)

    def test_a_timeout_is_reported_as_one_and_never_retried(self, states):
        states.begin(1)

        _run(states, profile_exceptions.TransferTimeoutError("slow"), will_retry=True)

        assert (states.get(1).status, states.get(1).failure) == (_Status.FAILED, _Failure.TIMED_OUT)

    def test_any_other_failure_is_final_with_a_sanitized_code(self, states):
        states.begin(1)

        _run(states, RuntimeError("secret detail"), will_retry=True)

        state = states.get(1)
        assert (state.status, state.failure) == (_Status.FAILED, _Failure.PROCESSING_FAILED)
        assert "secret" not in state.model_dump_json()


class TestOpenExport:
    def test_streams_the_staged_archive(self, states):
        states.begin(1)
        states.set_status(1, _Status.COMPLETED, size_bytes=8)
        storage = MagicMock()
        storage.open_stream.return_value = io.BytesIO(b"zip-data")

        chunks, size = job_service.open_export(1, states, storage)

        assert (b"".join(chunks), size) == (b"zip-data", 8)
        storage.open_stream.assert_called_once_with(_AREA, "1.zip")

    @pytest.mark.parametrize("status", [_Status.QUEUED, _Status.RUNNING, _Status.FAILED])
    def test_an_export_that_is_not_finished_has_no_download(self, states, status):
        states.begin(1)
        states.set_status(1, status)

        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(1, states, MagicMock())

    def test_a_missing_archive_is_not_found(self, states):
        states.begin(1)
        states.set_status(1, _Status.COMPLETED, size_bytes=8)
        storage = MagicMock()
        storage.open_stream.side_effect = FileNotFoundError

        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(1, states, storage)


class TestSweepStagedExports:
    def test_removes_only_archives_past_the_age(self):
        storage = MagicMock()
        now = time.time()
        storage.iter_objects.return_value = iter([("1.zip", now - 7200), ("2.zip", now)])

        removed = job_service.sweep_staged_exports(storage, 3600)

        assert removed == 1
        storage.delete.assert_called_once_with(_AREA, "1.zip")


class TestSweepSurvivesAFailedDelete:
    def test_one_failing_delete_does_not_stop_the_rest(self):
        storage = MagicMock()
        now = time.time()
        storage.iter_objects.return_value = iter([("1.zip", now - 100_000), ("2.zip", now - 100_000)])
        storage.delete.side_effect = [OSError("busy"), None]

        removed = job_service.sweep_staged_exports(storage, 3600)

        assert removed == 1
        assert storage.delete.call_count == 2


class TestDiscardStagedExport:
    def test_removes_the_users_archive(self):
        storage = MagicMock()

        job_service.discard_staged_export(7, storage)

        storage.delete.assert_called_once_with(_AREA, "7.zip")

    def test_a_storage_failure_is_logged_not_raised(self):
        storage = MagicMock()
        storage.delete.side_effect = OSError("down")

        job_service.discard_staged_export(7, storage)


class TestCloseDeadLetteredExport:
    @pytest.mark.parametrize("status", [_Status.QUEUED, _Status.RUNNING])
    def test_a_pending_export_is_failed_and_its_claim_released(self, states, status):
        states.begin(1)
        states.set_status(1, status)

        job_service.close_dead_lettered_export(_payload(1), states)

        assert states.get(1).status == _Status.FAILED
        assert states.get(1).failure == _Failure.PROCESSING_FAILED
        assert states.begin(1) is True

    def test_an_export_that_already_finished_keeps_its_outcome(self, states):
        states.begin(1)
        states.set_status(1, _Status.COMPLETED)

        job_service.close_dead_lettered_export(_payload(1), states)

        assert states.get(1).status == _Status.COMPLETED

    def test_an_expired_state_is_not_resurrected(self, states):
        job_service.close_dead_lettered_export(_payload(1), states)

        assert states.get(1) is None
