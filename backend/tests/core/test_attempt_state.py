"""Tests for core.attempt_state (provider-backed claim and polled state)."""

from enum import StrEnum
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from pydantic import BaseModel

import core.attempt_state as core_attempt_state


class _State(BaseModel):
    step: str


def _store(state=None, ttl=60) -> core_attempt_state.AttemptStateStore:
    return core_attempt_state.AttemptStateStore(state or MemoryState(), "feature", "job", ttl)


def test_keys_are_namespaced_by_feature_and_kind():
    state = MemoryState()
    store = _store(state)
    store.begin("1", _State(step="queued"))

    assert state.get(core_attempt_state.key("feature", "job:state", "1")) is not None
    assert state.get(core_attempt_state.key("feature", "job:claim", "1")) is not None
    assert core_attempt_state.key("garmin", "link:state", "1") == "endurain:garmin:link:state:1"


def test_a_second_begin_is_refused_until_the_attempt_finishes():
    store = _store()

    assert store.begin("1", _State(step="queued")) is True
    assert store.begin("1", _State(step="queued")) is False

    store.record("1", _State(step="done"), finished=True)

    assert store.begin("1", _State(step="queued")) is True


def test_subjects_and_features_do_not_block_each_other():
    state = MemoryState()
    store = _store(state)
    other_feature = core_attempt_state.AttemptStateStore(state, "other", "job", 60)
    store.begin("1", _State(step="queued"))

    assert store.begin("2", _State(step="queued")) is True
    assert other_feature.begin("1", _State(step="queued")) is True


def test_read_returns_the_recorded_state_or_none():
    store = _store()
    assert store.read("1") is None

    store.begin("1", _State(step="queued"))
    store.record("1", _State(step="running"), finished=False)

    assert _State.model_validate_json(store.read("1")) == _State(step="running")


def test_progress_renews_the_claim():
    state = MemoryState()
    store = _store(state)
    store.begin("1", _State(step="queued"))
    with patch.object(state, "set") as write:
        store.record("1", _State(step="running"), finished=False)

    assert core_attempt_state.key("feature", "job:claim", "1") in [call.args[0] for call in write.call_args_list]


def test_release_frees_the_claim_without_touching_the_state():
    store = _store()
    store.begin("1", _State(step="queued"))

    store.release("1")

    assert store.read("1") is not None
    assert store.begin("1", _State(step="queued")) is True


def test_discard_removes_the_claim_and_the_state():
    store = _store()
    store.begin("1", _State(step="queued"))

    store.discard("1")

    assert store.read("1") is None
    assert store.begin("1", _State(step="queued")) is True


def test_an_outage_while_discarding_is_swallowed():
    state = MemoryState()
    store = _store(state)
    store.begin("1", _State(step="queued"))
    with patch.object(state, "delete", side_effect=StateBackendUnavailableError("down")):
        store.discard("1")


def test_a_claim_is_not_left_behind_when_the_first_state_cannot_be_written():
    state = MemoryState()
    store = _store(state)
    with (
        patch.object(state, "set", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(core_attempt_state.StateUnavailableError),
    ):
        store.begin("1", _State(step="queued"))

    assert store.begin("1", _State(step="queued")) is True


def test_an_outage_on_read_is_a_service_unavailable_error():
    state = MemoryState()
    store = _store(state)
    with (
        patch.object(state, "get", side_effect=StateBackendUnavailableError("down")),
        pytest.raises(core_attempt_state.StateUnavailableError),
    ):
        store.read("1")


def test_an_outage_while_recording_or_releasing_is_swallowed():
    state = MemoryState()
    store = _store(state)
    store.begin("1", _State(step="queued"))
    with patch.object(state, "set", side_effect=StateBackendUnavailableError("down")):
        store.record("1", _State(step="running"), finished=False)
    with patch.object(state, "delete", side_effect=StateBackendUnavailableError("down")):
        store.release("1")


class _Kind(StrEnum):
    GEAR = "gear"
    HEALTH = "health"


Status = core_attempt_state.SyncStatus


def _syncs(state=None) -> core_attempt_state.SyncStateStore:
    return core_attempt_state.SyncStateStore(state or MemoryState(), "feature", 60)


class TestSyncStateStore:
    def test_a_first_sync_is_queued_and_blocks_another_of_its_kind(self):
        syncs = _syncs()

        assert syncs.begin(1, _Kind.GEAR) is True
        assert syncs.get(1, _Kind.GEAR) == core_attempt_state.SyncState(status=Status.QUEUED)
        assert syncs.begin(1, _Kind.GEAR) is False

    def test_progress_keeps_blocking_until_the_sync_finishes(self):
        syncs = _syncs()
        syncs.begin(1, _Kind.HEALTH)
        syncs.set_status(1, _Kind.HEALTH, Status.RUNNING)
        assert syncs.begin(1, _Kind.HEALTH) is False

        syncs.set_status(1, _Kind.HEALTH, Status.COMPLETED)

        assert syncs.get(1, _Kind.HEALTH).status == Status.COMPLETED
        assert syncs.begin(1, _Kind.HEALTH) is True

    def test_a_failed_sync_can_be_retried(self):
        syncs = _syncs()
        syncs.begin(1, _Kind.GEAR)
        syncs.set_status(1, _Kind.GEAR, Status.FAILED)

        assert syncs.begin(1, _Kind.GEAR) is True

    def test_a_discarded_sync_leaves_no_state_and_frees_the_claim(self):
        syncs = _syncs()
        syncs.begin(1, _Kind.GEAR)

        syncs.discard(1, _Kind.GEAR)

        assert syncs.get(1, _Kind.GEAR) is None
        assert syncs.begin(1, _Kind.GEAR) is True

    def test_kinds_users_and_features_do_not_block_each_other(self):
        state = MemoryState()
        syncs = _syncs(state)
        syncs.begin(1, _Kind.GEAR)

        assert syncs.begin(1, _Kind.HEALTH) is True
        assert syncs.begin(2, _Kind.GEAR) is True
        assert core_attempt_state.SyncStateStore(state, "other", 60).begin(1, _Kind.GEAR) is True

    def test_the_keys_are_the_ones_each_feature_always_used(self):
        state = MemoryState()
        _syncs(state).begin(7, _Kind.GEAR)

        assert state.get("endurain:feature:sync:state:7:gear") is not None
        assert state.get("endurain:feature:sync:claim:7:gear") is not None

    def test_no_sync_reads_as_none(self):
        assert _syncs().get(99, _Kind.GEAR) is None

    @pytest.mark.parametrize("pending", [Status.QUEUED, Status.RUNNING])
    def test_a_pending_sync_is_closed_as_failed_and_frees_the_claim(self, pending):
        syncs = _syncs()
        syncs.begin(1, _Kind.GEAR)
        syncs.set_status(1, _Kind.GEAR, pending)

        assert syncs.close_pending(1, _Kind.GEAR) is True
        assert syncs.get(1, _Kind.GEAR).status == Status.FAILED
        assert syncs.begin(1, _Kind.GEAR) is True

    @pytest.mark.parametrize("finished", [Status.COMPLETED, Status.FAILED])
    def test_a_finished_sync_is_left_as_it_is(self, finished):
        syncs = _syncs()
        syncs.begin(1, _Kind.GEAR)
        syncs.set_status(1, _Kind.GEAR, finished)

        assert syncs.close_pending(1, _Kind.GEAR) is False
        assert syncs.get(1, _Kind.GEAR).status == finished

    def test_an_expired_sync_is_left_alone(self):
        assert _syncs().close_pending(1, _Kind.GEAR) is False

    def test_an_unavailable_backend_fails_a_read_and_a_begin_but_not_a_recorded_outcome(self):
        state = MagicMock()
        for method in ("set", "get", "delete", "set_if_absent"):
            getattr(state, method).side_effect = StateBackendUnavailableError("down")
        syncs = _syncs(state)

        with pytest.raises(core_attempt_state.StateUnavailableError):
            syncs.begin(1, _Kind.GEAR)
        with pytest.raises(core_attempt_state.StateUnavailableError):
            syncs.get(1, _Kind.GEAR)
        syncs.set_status(1, _Kind.GEAR, Status.COMPLETED)
