"""Tests for garmin.sync_state_store (provider-backed)."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import modules.garmin.constants as garmin_constants
import modules.garmin.sync_state_store as sync_state_store

Kind = garmin_constants.SyncKind
Status = garmin_constants.SyncStatus


def _store() -> sync_state_store.GarminSyncStateStore:
    return sync_state_store.GarminSyncStateStore(state=MemoryState())


def test_a_first_sync_is_queued_and_blocks_another_of_its_kind():
    store = _store()

    assert store.begin(1, Kind.GEAR) is True
    assert store.get(1, Kind.GEAR) == core_attempt_state.SyncState(status=Status.QUEUED)
    assert store.begin(1, Kind.GEAR) is False


def test_progress_keeps_blocking_until_the_sync_finishes():
    store = _store()
    store.begin(1, Kind.HEALTH)
    store.set_status(1, Kind.HEALTH, Status.RUNNING)
    assert store.begin(1, Kind.HEALTH) is False

    store.set_status(1, Kind.HEALTH, Status.COMPLETED)

    assert store.get(1, Kind.HEALTH).status == Status.COMPLETED
    assert store.begin(1, Kind.HEALTH) is True


def test_a_failed_sync_can_be_retried():
    store = _store()
    store.begin(1, Kind.GEAR)
    store.set_status(1, Kind.GEAR, Status.FAILED)

    assert store.begin(1, Kind.GEAR) is True


def test_kinds_and_users_do_not_block_each_other():
    store = _store()
    store.begin(1, Kind.GEAR)

    assert store.begin(1, Kind.HEALTH) is True
    assert store.begin(2, Kind.GEAR) is True


def test_no_sync_reads_as_none():
    assert _store().get(99, Kind.GEAR) is None


def test_an_unavailable_backend_fails_a_read_and_a_begin_but_not_a_recorded_outcome():
    state = MagicMock()
    for method in ("set", "get", "delete", "set_if_absent"):
        getattr(state, method).side_effect = StateBackendUnavailableError("down")
    store = sync_state_store.GarminSyncStateStore(state=state)

    with pytest.raises(core_attempt_state.StateUnavailableError):
        store.begin(1, Kind.GEAR)
    with pytest.raises(core_attempt_state.StateUnavailableError):
        store.get(1, Kind.GEAR)
    store.set_status(1, Kind.GEAR, Status.COMPLETED)
