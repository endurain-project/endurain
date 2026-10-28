"""Tests for the shared state machine of a queued provider sync."""

from enum import StrEnum
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.sync_runner as core_sync_runner

Status = core_attempt_state.SyncStatus


class _Kinds(StrEnum):
    GEAR = "gear"


@pytest.fixture
def states():
    return core_attempt_state.SyncStateStore(MemoryState(), "feature", 60)


def _begin(states):
    assert states.begin(1, _Kinds.GEAR)


class TestRunRecorded:
    def test_a_sync_that_did_something_is_completed(self, states):
        _begin(states)

        result = core_sync_runner.run_recorded(states, 1, _Kinds.GEAR, lambda: True, will_retry=False)

        assert result is True
        assert states.get(1, _Kinds.GEAR).status == Status.COMPLETED

    def test_a_sync_with_nothing_to_do_is_recorded_as_failed(self, states):
        _begin(states)

        result = core_sync_runner.run_recorded(states, 1, _Kinds.GEAR, lambda: False, will_retry=False)

        assert result is False
        assert states.get(1, _Kinds.GEAR).status == Status.FAILED

    def test_the_sync_is_running_while_the_work_runs(self, states):
        _begin(states)
        seen = []

        core_sync_runner.run_recorded(
            states, 1, _Kinds.GEAR, lambda: seen.append(states.get(1, _Kinds.GEAR).status) or True, will_retry=False
        )

        assert seen == [Status.RUNNING]

    def test_a_refusal_is_recorded_as_failed_and_not_raised(self, states):
        _begin(states)
        refused = MagicMock()

        def work():
            raise core_exceptions.TooManyRequestsError("limited")

        result = core_sync_runner.run_recorded(
            states,
            1,
            _Kinds.GEAR,
            work,
            will_retry=True,
            refusals=(core_exceptions.TooManyRequestsError,),
            on_refused=refused,
        )

        assert result is None
        assert states.get(1, _Kinds.GEAR).status == Status.FAILED
        refused.assert_called_once()

    def test_a_failure_a_worker_will_retry_stays_queued_and_raises(self, states):
        _begin(states)

        def work():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            core_sync_runner.run_recorded(states, 1, _Kinds.GEAR, work, will_retry=True)

        assert states.get(1, _Kinds.GEAR).status == Status.QUEUED
        assert states.begin(1, _Kinds.GEAR) is False

    def test_a_failure_nothing_retries_is_failed_and_raises(self, states):
        _begin(states)

        def work():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            core_sync_runner.run_recorded(states, 1, _Kinds.GEAR, work, will_retry=False)

        assert states.get(1, _Kinds.GEAR).status == Status.FAILED
        assert states.begin(1, _Kinds.GEAR) is True


class TestQueueSync:
    def test_a_durable_sync_is_published(self, states):
        publish, submit = MagicMock(), MagicMock()

        core_sync_runner.queue_sync(states, 1, _Kinds.GEAR, "Provider", durable=True, publish=publish, submit=submit)

        publish.assert_called_once_with()
        submit.assert_not_called()
        assert states.get(1, _Kinds.GEAR).status == Status.QUEUED

    def test_a_local_sync_is_submitted_to_the_pool(self, states):
        publish, submit = MagicMock(), MagicMock()

        core_sync_runner.queue_sync(states, 1, _Kinds.GEAR, "Provider", durable=False, publish=publish, submit=submit)

        submit.assert_called_once_with()
        publish.assert_not_called()

    def test_a_pending_sync_is_a_conflict(self, states):
        _begin(states)

        with pytest.raises(core_exceptions.ConflictError, match="Provider gear sync is already in progress"):
            core_sync_runner.queue_sync(
                states, 1, _Kinds.GEAR, "Provider", durable=True, publish=MagicMock(), submit=MagicMock()
            )

    def test_a_failure_to_queue_frees_the_claim(self, states):
        with pytest.raises(RuntimeError):
            core_sync_runner.queue_sync(
                states,
                1,
                _Kinds.GEAR,
                "Provider",
                durable=True,
                publish=MagicMock(side_effect=RuntimeError("boom")),
                submit=MagicMock(),
            )

        assert states.get(1, _Kinds.GEAR).status == Status.FAILED
        assert states.begin(1, _Kinds.GEAR) is True


class TestStatusAndDeadLetter:
    def test_status_is_not_found_when_none_is_recorded(self, states):
        with pytest.raises(core_exceptions.NotFoundError, match="No Provider gear sync recorded"):
            core_sync_runner.read_state(states, 1, _Kinds.GEAR, "Provider")

    def test_status_reports_the_recorded_state(self, states):
        _begin(states)

        assert core_sync_runner.read_state(states, 1, _Kinds.GEAR, "Provider").status == Status.QUEUED

    def test_a_dead_lettered_sync_is_failed_and_its_claim_freed(self, states):
        _begin(states)

        core_sync_runner.close_dead_lettered(states, 1, _Kinds.GEAR, "Provider")

        assert states.get(1, _Kinds.GEAR).status == Status.FAILED
        assert states.begin(1, _Kinds.GEAR) is True
