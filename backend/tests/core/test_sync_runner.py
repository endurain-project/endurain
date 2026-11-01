"""Tests for the shared state machine of a queued provider sync."""

from enum import StrEnum
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.event_versioning import VersionedPayload
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

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


class TestStartClaimed:
    def test_a_claimed_start_runs(self):
        start, release = MagicMock(), MagicMock()

        core_sync_runner.start_claimed(lambda: True, "busy", start, release)

        start.assert_called_once_with()
        release.assert_not_called()

    def test_a_held_claim_is_a_conflict_and_nothing_starts(self):
        start = MagicMock()

        with pytest.raises(core_exceptions.ConflictError, match="busy"):
            core_sync_runner.start_claimed(lambda: False, "busy", start, MagicMock())

        start.assert_not_called()

    def test_a_start_that_fails_releases_the_claim(self):
        release = MagicMock()

        with pytest.raises(RuntimeError):
            core_sync_runner.start_claimed(lambda: True, "busy", MagicMock(side_effect=RuntimeError("boom")), release)

        release.assert_called_once_with()


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


class _Payload(VersionedPayload):
    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int


def _event(retry_count: int) -> Event:
    return Event(
        event_id="evt-1",
        event_type="feature.sync_requested",
        source="test",
        timestamp="2026-10-31T00:00:00+00:00",
        payload={"user_id": 7},
        retry_count=retry_count,
        max_attempts=3,
    )


class TestRegisterSyncJob:
    @pytest.fixture
    def handlers(self):
        run, close = MagicMock(), MagicMock()
        registry = JobHandlerRegistry()
        core_sync_runner.register_sync_job(
            registry, "feature.sync_requested", "feature.sync", _Payload, run=run, close=close
        )
        return registry, run, close

    @pytest.mark.parametrize(("retry_count", "will_retry"), [(1, True), (2, True), (3, False)])
    def test_the_job_asks_for_a_retry_only_while_attempts_remain(self, handlers, retry_count, will_retry):
        registry, run, _close = handlers

        registry.get("feature.sync")(_event(retry_count))

        run.assert_called_once_with(_Payload(user_id=7), will_retry)

    def test_a_dead_lettered_job_closes_its_sync(self, handlers):
        registry, _run, close = handlers

        registry.dead_letter_callback("feature.sync")(_event(3), "lease expired")

        close.assert_called_once_with(_Payload(user_id=7))
