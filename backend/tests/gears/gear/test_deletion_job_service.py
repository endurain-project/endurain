"""Tests for gear.deletion_job_service: accepting, running and closing a gear deletion."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.crud as crud
import modules.gears.gear.deletion_job_service as job_service
import modules.gears.gear.deletion_state_store as deletion_state_store
import modules.gears.gear.events as gears_events
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.gears import gear_create, install_readers

_GEAR_ID = uuid.UUID(int=7)
_MODULE = "modules.gears.gear.deletion_job_service"
_Status = core_job_status.JobState
_BATCH = gears_constants.DELETION_BATCH_SIZE


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def states(state):
    return deletion_state_store.GearDeletionStateStore(state)


def _payload(job_id: uuid.UUID, gear_id: uuid.UUID = _GEAR_ID) -> gears_events.DeletionRequestedPayload:
    return gears_events.DeletionRequestedPayload(user_id=MOCK_USER_ID, gear_id=gear_id, job_id=job_id)


def _supersede(states, state):
    """Free the running deletion's claim as an expiry would, then begin a newer one; return the newer job."""
    state.delete(core_attempt_state.key("gears", "deletion:claim", str(_GEAR_ID)))
    return states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")


class TestRequestGearDeletion:
    def _request(self, states, db, gear, *, jobs_enabled=True, if_match=None):
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=jobs_enabled)),
            patch(f"{_MODULE}.gears_event_publishers") as publishers,
            patch(f"{_MODULE}._pool") as pool,
        ):
            result = job_service.request_gear_deletion(
                gear.id, MOCK_USER_ID, states, db, if_match=if_match or f'"{gear.version}"'
            )
        return result, publishers, pool

    def test_a_durable_request_publishes_the_work_and_answers_queued(self, states, db):
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)

        result, publishers, pool = self._request(states, db, gear)

        assert (result.kind, result.status) == (gears_constants.DELETION_JOB, _Status.QUEUED)
        publishers.publish_deletion_requested.assert_called_once_with(
            gear.id, MOCK_USER_ID, result.id, db, commit=db.commit
        )
        pool.submit.assert_not_called()
        assert states.get(gear.id).status == _Status.QUEUED

    def test_without_durable_jobs_the_work_runs_on_the_pool(self, states, db):
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)

        _, publishers, pool = self._request(states, db, gear, jobs_enabled=False)

        pool.require_capacity.assert_called_once_with()
        pool.submit.assert_called_once()
        publishers.publish_deletion_requested.assert_not_called()

    def test_a_stale_version_is_refused_before_anything_is_queued(self, states, db):
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._request(states, db, gear, if_match='"99"')

        assert states.get(gear.id) is None

    def test_a_foreign_or_missing_gear_is_not_found_before_anything_is_queued(self, states, db):
        gear = crud.create_gear(gear_create(), uuid.UUID(int=99), db)

        with pytest.raises(core_exceptions.NotFoundError):
            self._request(states, db, gear)

        assert states.get(gear.id) is None

    def test_a_pending_deletion_is_refused_naming_the_running_job(self, states, db):
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        running = states.begin(gear.id, MOCK_USER_ID, conflict="x")

        with pytest.raises(core_exceptions.JobAlreadyRunningError) as refused:
            self._request(states, db, gear)

        assert refused.value.job_id == running.id

    def test_a_failure_before_the_job_starts_frees_the_claim(self, states, db):
        gear = crud.create_gear(gear_create(), MOCK_USER_ID, db)
        with (
            patch(f"{_MODULE}.core_config.settings", MagicMock(JOBS_ENABLED=True)),
            patch(f"{_MODULE}.gears_event_publishers") as publishers,
            pytest.raises(RuntimeError),
        ):
            publishers.publish_deletion_requested.side_effect = RuntimeError("boom")
            job_service.request_gear_deletion(gear.id, MOCK_USER_ID, states, db, if_match=f'"{gear.version}"')

        assert states.get(gear.id).status == _Status.FAILED
        states.begin(gear.id, MOCK_USER_ID, conflict="x")


class TestRunGearDeletion:
    def _run(self, states, job_id, *, cleared, delete_error=None, will_retry=False):
        clear = MagicMock(side_effect=cleared)
        install_readers(clear_activities_gear=clear)
        with (
            patch(f"{_MODULE}.core_database.SessionLocal") as session_local,
            patch(f"{_MODULE}.gears_service") as service,
        ):
            service.delete_gear.side_effect = delete_error
            job_service.run_gear_deletion(_payload(job_id), states, will_retry=will_retry)
        return clear, service, session_local

    def test_it_unassigns_batch_by_batch_then_deletes_the_gear(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

        clear, service, session_local = self._run(states, job.id, cleared=[_BATCH, _BATCH, 3])

        assert clear.call_count == 3
        assert clear.call_args.args[:3] == (_GEAR_ID, MOCK_USER_ID, _BATCH)
        # Every batch commits in a transaction of its own.
        assert session_local.return_value.__enter__.return_value.commit.call_count == 3
        service.delete_gear.assert_called_once()
        assert service.delete_gear.call_args.args[:2] == (_GEAR_ID, MOCK_USER_ID)
        assert states.get(_GEAR_ID).status == _Status.SUCCEEDED

    def test_a_gear_with_no_activities_is_deleted_after_one_empty_batch(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

        clear, service, _ = self._run(states, job.id, cleared=[0])

        assert clear.call_count == 1
        service.delete_gear.assert_called_once()

    def test_a_gear_that_is_already_gone_ends_as_succeeded(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

        self._run(states, job.id, cleared=[0], delete_error=core_exceptions.NotFoundError("Gear not found"))

        assert states.get(_GEAR_ID).status == _Status.SUCCEEDED

    def test_a_deletion_that_is_not_pending_is_skipped(self, states):
        clear, service, _ = self._run(states, uuid.uuid4(), cleared=[0])

        clear.assert_not_called()
        service.delete_gear.assert_not_called()

    def test_a_failure_nothing_retries_fails_the_deletion_and_frees_the_claim(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

        self._run(states, job.id, cleared=RuntimeError("boom"))

        assert states.get(_GEAR_ID).status == _Status.FAILED
        states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

    def test_a_failure_a_worker_will_retry_stays_queued_and_raises(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

        with pytest.raises(RuntimeError):
            self._run(states, job.id, cleared=RuntimeError("boom"), will_retry=True)

        assert states.get(_GEAR_ID).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")


class TestDeadLetter:
    def test_a_dead_lettered_deletion_is_failed_and_its_claim_freed(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

        job_service.close_dead_lettered_deletion(_payload(job.id), states)

        assert states.get(_GEAR_ID).status == _Status.FAILED
        states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")

    def test_a_finished_deletion_is_left_alone(self, states):
        job = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")
        states.set_status(_GEAR_ID, job.id, _Status.SUCCEEDED)

        job_service.close_dead_lettered_deletion(_payload(job.id), states)

        assert states.get(_GEAR_ID).status == _Status.SUCCEEDED

    def test_a_superseded_deletion_leaves_the_newer_one_alone(self, states, state):
        old = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")
        new = _supersede(states, state)

        job_service.close_dead_lettered_deletion(_payload(old.id), states)

        assert states.get(_GEAR_ID, job_id=new.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")


class TestSuperseded:
    def test_running_a_superseded_deletion_leaves_the_newer_one_alone(self, states, state):
        old = states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")
        new = _supersede(states, state)
        clear = MagicMock(side_effect=[0])
        install_readers(clear_activities_gear=clear)
        with (
            patch(f"{_MODULE}.core_database.SessionLocal"),
            patch(f"{_MODULE}.gears_service") as service,
        ):
            job_service.run_gear_deletion(_payload(old.id), states)

        clear.assert_not_called()
        service.delete_gear.assert_not_called()
        assert states.get(_GEAR_ID, job_id=new.id).status == _Status.QUEUED
        with pytest.raises(core_exceptions.JobAlreadyRunningError):
            states.begin(_GEAR_ID, MOCK_USER_ID, conflict="x")
