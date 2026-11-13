"""Tests for users_profile.export_job_service: accepting, running, serving and sweeping profile exports."""

import io
import time
import uuid
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.export_job_service as job_service
import modules.users.users_profile.export_state_store as export_state_store

_MODULE = "modules.users.users_profile.export_job_service"
_Status = profile_constants.ExportStatus
_Failure = profile_constants.ExportFailure
_AREA = profile_constants.EXPORT_STAGING_AREA
_USER_ID = uuid.UUID(int=1)
_SESSION_ID = uuid.UUID(int=601)


@pytest.fixture
def states():
    return export_state_store.ProfileExportStateStore(MemoryState())


@pytest.fixture
def verify_step_up():
    with patch(f"{_MODULE}.account_security_integration.verify_step_up") as verify:
        yield verify


def _request(states, db):
    return job_service.request_export(
        _USER_ID, _SESSION_ID, auth_schema.StepUpVerification(current_password="pw"), MagicMock(), states, db
    )


def _payload(user_id: uuid.UUID = _USER_ID) -> profile_events.ProfileExportRequestedPayload:
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
    def test_a_full_local_pool_refuses_before_the_claim_is_taken(self, states, mock_db, verify_step_up):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=False)),
            patch(f"{_MODULE}.profile_transfer_pool.pool") as pool,
        ):
            pool.require_capacity.side_effect = core_exceptions.ServiceUnavailableError("full")
            with pytest.raises(core_exceptions.ServiceUnavailableError):
                _request(states, mock_db)

        assert states.get(_USER_ID) is None

    def test_a_durable_deployment_does_not_look_at_the_local_pool(self, states, mock_db, verify_step_up):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=True)),
            patch(f"{_MODULE}.profile_transfer_pool.pool") as pool,
            patch(f"{_MODULE}.profile_event_publishers.publish_export_requested"),
        ):
            _request(states, mock_db)

        pool.require_capacity.assert_not_called()

    def test_an_export_the_pool_could_not_take_is_closed(self, states):
        states.begin(_USER_ID, conflict="held")

        job_service.fail_unstarted_export(_payload(), states)

        assert states.get(_USER_ID).status == _Status.FAILED
        assert states.get(_USER_ID).error_code == _Failure.PROCESSING_FAILED

    def test_queues_the_export(self, states, mock_db, verify_step_up):
        with patch(f"{_MODULE}.profile_event_publishers.publish_export_requested") as publish:
            state = _request(states, mock_db)

        assert state.status == _Status.QUEUED
        publish.assert_called_once_with(_USER_ID, mock_db, commit=mock_db.commit)

    def test_a_pending_export_refuses_a_second(self, states, mock_db, verify_step_up):
        states.begin(_USER_ID, conflict="held")

        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            _request(states, mock_db)

    def test_a_failure_to_queue_closes_the_state_and_frees_the_claim(self, states, mock_db, verify_step_up):
        with (
            patch(f"{_MODULE}.profile_event_publishers.publish_export_requested", side_effect=RuntimeError("down")),
            pytest.raises(RuntimeError),
        ):
            _request(states, mock_db)

        assert states.get(_USER_ID).status == _Status.FAILED
        states.begin(_USER_ID, conflict="held")

    def test_the_step_up_is_verified_for_this_action_before_anything_is_claimed(self, states, mock_db, verify_step_up):
        verify_step_up.side_effect = core_exceptions.UnauthenticatedError("Invalid credentials")

        with (
            patch(f"{_MODULE}.profile_event_publishers.publish_export_requested") as publish,
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _request(states, mock_db)

        publish.assert_not_called()
        assert states.get(_USER_ID) is None
        assert verify_step_up.call_args.args[1:4] == (
            _USER_ID,
            _SESSION_ID,
            identity_providers_constants.StepUpAction.PROFILE_EXPORT,
        )


class TestRunExport:
    def test_a_finished_export_records_its_size(self, states):
        states.begin(_USER_ID, conflict="held")

        _run(states, 42)

        state = states.get(_USER_ID)
        assert (state.status, state.size_bytes) == (_Status.SUCCEEDED, 42)
        states.begin(_USER_ID, conflict="held")

    @pytest.mark.parametrize("finished", [_Status.SUCCEEDED, _Status.FAILED])
    def test_a_redelivery_of_a_finished_export_does_nothing(self, states, finished):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, finished)

        stage = _run(states, 1)

        stage.assert_not_called()

    def test_a_redelivery_after_a_worker_died_builds_again(self, states):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, _Status.RUNNING)

        stage = _run(states, 5)

        stage.assert_called_once()
        assert states.get(_USER_ID).status == _Status.SUCCEEDED

    def test_a_transient_failure_is_retried(self, states):
        states.begin(_USER_ID, conflict="held")

        with pytest.raises(OperationalError):
            _run(states, OperationalError("s", {}, Exception("db down")), will_retry=True)

        assert states.get(_USER_ID).status == _Status.QUEUED

    def test_a_database_failure_wrapped_by_the_collection_is_retried(self, states):
        states.begin(_USER_ID, conflict="held")
        try:
            raise OperationalError("s", {}, Exception("db down"))
        except OperationalError as db_err:
            wrapped = profile_exceptions.TransferUnprocessableError("Data collection failed")
            wrapped.__cause__ = db_err

        with pytest.raises(profile_exceptions.TransferUnprocessableError):
            _run(states, wrapped, will_retry=True)

        assert states.get(_USER_ID).status == _Status.QUEUED

    def test_a_transient_failure_on_the_last_attempt_is_final(self, states):
        states.begin(_USER_ID, conflict="held")

        _run(states, OperationalError("s", {}, Exception("db down")), will_retry=False)

        assert (states.get(_USER_ID).status, states.get(_USER_ID).error_code) == (
            _Status.FAILED,
            _Failure.PROCESSING_FAILED,
        )

    def test_a_timeout_is_reported_as_one_and_never_retried(self, states):
        states.begin(_USER_ID, conflict="held")

        _run(states, profile_exceptions.TransferTimeoutError("slow"), will_retry=True)

        assert (states.get(_USER_ID).status, states.get(_USER_ID).error_code) == (_Status.FAILED, _Failure.TIMED_OUT)

    def test_any_other_failure_is_final_with_a_sanitized_code(self, states):
        states.begin(_USER_ID, conflict="held")

        _run(states, RuntimeError("secret detail"), will_retry=True)

        state = states.get(_USER_ID)
        assert (state.status, state.error_code) == (_Status.FAILED, _Failure.PROCESSING_FAILED)
        assert "secret" not in state.model_dump_json()


class TestOpenExport:
    def test_streams_the_staged_archive(self, states):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, _Status.SUCCEEDED, size_bytes=8)
        storage = MagicMock()
        storage.open_stream.return_value = io.BytesIO(b"zip-data")

        chunks, size = job_service.open_export(_USER_ID, states, storage)

        assert (b"".join(chunks), size) == (b"zip-data", 8)
        storage.open_stream.assert_called_once_with(_AREA, f"{_USER_ID}.zip")

    @pytest.mark.parametrize("status", [_Status.QUEUED, _Status.RUNNING, _Status.FAILED])
    def test_an_export_that_is_not_finished_has_no_download(self, states, status):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, status)

        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(_USER_ID, states, MagicMock())

    def test_a_missing_archive_is_not_found(self, states):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, _Status.SUCCEEDED, size_bytes=8)
        storage = MagicMock()
        storage.open_stream.side_effect = FileNotFoundError

        with pytest.raises(core_exceptions.NotFoundError):
            job_service.open_export(_USER_ID, states, storage)


class TestSweepStagedExports:
    def test_removes_only_archives_past_the_age(self):
        storage = MagicMock()
        now = time.time()
        storage.iter_objects.return_value = iter([(f"{_USER_ID}.zip", now - 7200), ("2.zip", now)])

        removed = job_service.sweep_staged_exports(storage, 3600)

        assert removed == 1
        storage.delete.assert_called_once_with(_AREA, f"{_USER_ID}.zip")


class TestSweepSurvivesAFailedDelete:
    def test_one_failing_delete_does_not_stop_the_rest(self):
        storage = MagicMock()
        now = time.time()
        storage.iter_objects.return_value = iter([(f"{_USER_ID}.zip", now - 100_000), ("2.zip", now - 100_000)])
        storage.delete.side_effect = [platform_providers.StorageBackendUnavailableError("busy"), None]

        removed = job_service.sweep_staged_exports(storage, 3600)

        assert removed == 1
        assert storage.delete.call_count == 2


class TestDiscardStagedExport:
    def test_removes_the_users_archive(self):
        storage = MagicMock()

        job_service.discard_staged_export(_USER_ID, storage)

        storage.delete.assert_called_once_with(_AREA, f"{_USER_ID}.zip")

    def test_a_storage_failure_is_logged_not_raised(self):
        storage = MagicMock()
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("down")

        job_service.discard_staged_export(_USER_ID, storage)

        storage.delete.assert_called_once()

    def test_an_unexpected_error_propagates(self):
        storage = MagicMock()
        storage.delete.side_effect = TypeError("bug")

        with pytest.raises(TypeError):
            job_service.discard_staged_export(_USER_ID, storage)


class TestCloseDeadLetteredExport:
    @pytest.mark.parametrize("status", [_Status.QUEUED, _Status.RUNNING])
    def test_a_pending_export_is_failed_and_its_claim_released(self, states, status):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, status)

        job_service.close_dead_lettered_export(_payload(), states)

        assert states.get(_USER_ID).status == _Status.FAILED
        assert states.get(_USER_ID).error_code == _Failure.PROCESSING_FAILED
        states.begin(_USER_ID, conflict="held")

    def test_an_export_that_already_finished_keeps_its_outcome(self, states):
        states.begin(_USER_ID, conflict="held")
        states.set_status(_USER_ID, _Status.SUCCEEDED)

        job_service.close_dead_lettered_export(_payload(), states)

        assert states.get(_USER_ID).status == _Status.SUCCEEDED

    def test_an_expired_state_is_not_resurrected(self, states):
        job_service.close_dead_lettered_export(_payload(), states)

        assert states.get(_USER_ID) is None
