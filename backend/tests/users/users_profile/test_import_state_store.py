"""Tests for users_profile.import_state_store (provider-backed)."""

from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.import_state_store as import_state_store

Status = profile_constants.ImportStatus


def _store(state=None):
    return import_state_store.ProfileImportStateStore(state or MemoryState())


def test_begin_records_queued_and_refuses_a_second_import():
    store = _store()

    assert store.begin(1) is True
    assert store.get(1) == import_state_store.ProfileImportState(status=Status.QUEUED)
    assert store.begin(1) is False


def test_users_do_not_block_each_other():
    store = _store()
    store.begin(1)

    assert store.begin(2) is True


def test_progress_keeps_the_claim_and_a_finished_import_releases_it():
    store = _store()
    store.begin(1)

    store.set_status(1, Status.RUNNING)
    assert store.begin(1) is False

    store.set_status(1, Status.COMPLETED, imported={"gears": 2})
    assert store.get(1).imported == {"gears": 2}
    assert store.begin(1) is True


def test_a_failure_carries_its_code():
    store = _store()
    store.begin(1)

    store.set_status(1, Status.FAILED, failure=profile_constants.ImportFailure.TOO_LARGE)

    assert store.get(1).failure == profile_constants.ImportFailure.TOO_LARGE


def test_state_lives_under_the_users_namespace():
    state = MemoryState()
    _store(state).begin(5)

    assert state.get(core_attempt_state.key("users", "profile_import:state", "5")) is not None


def test_a_strict_status_raises_when_storage_is_down_and_a_plain_one_does_not():
    state = MagicMock()
    state.set.side_effect = StateBackendUnavailableError("down")
    store = _store(state)

    store.set_status(1, Status.RUNNING)
    with pytest.raises(core_attempt_state.StateUnavailableError):
        store.set_status(1, Status.WRITING_FILES, strict=True)
