"""Tests for garmin.sync_state_store (provider-backed)."""

import uuid
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.sync_state_store as sync_state_store
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

Kind = garmin_constants.SyncKind
Status = garmin_constants.SyncStatus


def _store() -> sync_state_store.GarminSyncStateStore:
    return sync_state_store.GarminSyncStateStore(state=MemoryState())


def test_a_first_sync_is_queued_and_blocks_another_of_its_kind():
    store = _store()

    store.begin(MOCK_USER_ID, Kind.GEAR, conflict="busy")
    assert store.get(MOCK_USER_ID, Kind.GEAR) == core_attempt_state.SyncState(status=Status.QUEUED)
    with pytest.raises(core_exceptions.JobAlreadyRunningError):
        store.begin(MOCK_USER_ID, Kind.GEAR, conflict="busy")


def test_progress_keeps_blocking_until_the_sync_finishes():
    store = _store()
    store.begin(MOCK_USER_ID, Kind.HEALTH, conflict="busy")
    store.set_status(MOCK_USER_ID, Kind.HEALTH, Status.RUNNING)
    with pytest.raises(core_exceptions.JobAlreadyRunningError):
        store.begin(MOCK_USER_ID, Kind.HEALTH, conflict="busy")

    store.set_status(MOCK_USER_ID, Kind.HEALTH, Status.SUCCEEDED)

    assert store.get(MOCK_USER_ID, Kind.HEALTH).status == Status.SUCCEEDED
    store.begin(MOCK_USER_ID, Kind.HEALTH, conflict="busy")


def test_a_failed_sync_can_be_retried():
    store = _store()
    store.begin(MOCK_USER_ID, Kind.GEAR, conflict="busy")
    store.set_status(MOCK_USER_ID, Kind.GEAR, Status.FAILED)

    store.begin(MOCK_USER_ID, Kind.GEAR, conflict="busy")


def test_kinds_and_users_do_not_block_each_other():
    store = _store()
    store.begin(MOCK_USER_ID, Kind.GEAR, conflict="busy")

    store.begin(MOCK_USER_ID, Kind.HEALTH, conflict="busy")
    store.begin(OTHER_USER_ID, Kind.GEAR, conflict="busy")


def test_no_sync_reads_as_none():
    assert _store().get(uuid.UUID(int=99), Kind.GEAR) is None


def test_an_unavailable_backend_fails_a_read_and_a_begin_but_not_a_recorded_outcome():
    state = MagicMock()
    for method in ("set", "get", "delete", "set_if_absent"):
        getattr(state, method).side_effect = StateBackendUnavailableError("down")
    store = sync_state_store.GarminSyncStateStore(state=state)

    with pytest.raises(core_attempt_state.StateUnavailableError):
        store.begin(MOCK_USER_ID, Kind.GEAR, conflict="busy")
    with pytest.raises(core_attempt_state.StateUnavailableError):
        store.get(MOCK_USER_ID, Kind.GEAR)
    store.set_status(MOCK_USER_ID, Kind.GEAR, Status.SUCCEEDED)
