"""Tests for users_profile.import_state_store (provider-backed)."""

import uuid
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.import_state_store as import_state_store

Status = profile_constants.ImportStatus
_USER_ID = uuid.UUID(int=1)
_OTHER_USER_ID = uuid.UUID(int=2)


def _store(state=None):
    return import_state_store.ProfileImportStateStore(state or MemoryState())


def test_begin_records_queued_and_refuses_a_second_import():
    store = _store()

    store.begin(_USER_ID, conflict="held")
    assert store.get(_USER_ID) == import_state_store.ProfileImportState(status=Status.QUEUED)
    with pytest.raises(core_exceptions.JobAlreadyRunningError):
        store.begin(_USER_ID, conflict="held")


def test_users_do_not_block_each_other():
    store = _store()
    store.begin(_USER_ID, conflict="held")

    store.begin(_OTHER_USER_ID, conflict="held")


def test_progress_keeps_the_claim_and_a_finished_import_releases_it():
    store = _store()
    store.begin(_USER_ID, conflict="held")

    store.set_status(_USER_ID, Status.RUNNING)
    with pytest.raises(core_exceptions.JobAlreadyRunningError):
        store.begin(_USER_ID, conflict="held")

    store.set_status(_USER_ID, Status.SUCCEEDED, imported={"gears": 2})
    assert store.get(_USER_ID).imported == {"gears": 2}
    store.begin(_USER_ID, conflict="held")


def test_a_failure_carries_its_code():
    store = _store()
    store.begin(_USER_ID, conflict="held")

    store.set_status(_USER_ID, Status.FAILED, error_code=profile_constants.ImportFailure.TOO_LARGE)

    assert store.get(_USER_ID).error_code == profile_constants.ImportFailure.TOO_LARGE


def test_state_lives_under_the_users_namespace():
    state = MemoryState()
    _store(state).begin(_USER_ID, conflict="held")

    assert state.get(core_attempt_state.key("users", "profile_import:state", str(_USER_ID))) is not None


def test_a_strict_status_raises_when_storage_is_down_and_a_plain_one_does_not():
    state = MemoryState()
    store = _store(state)
    store.begin(_USER_ID, conflict="held")
    state.set = MagicMock(side_effect=StateBackendUnavailableError("down"))

    store.set_status(_USER_ID, Status.RUNNING)
    with pytest.raises(core_attempt_state.StateUnavailableError):
        store.set_status(_USER_ID, Status.WRITING_FILES, strict=True)


def test_an_import_state_stored_with_the_old_names_reads_as_the_new_ones():
    done = import_state_store.ProfileImportState.model_validate_json(b'{"status":"completed","imported":{"gears":2}}')
    failed = import_state_store.ProfileImportState.model_validate_json(
        b'{"status":"failed","failure":"files_incomplete"}'
    )

    assert (done.status, done.imported) == (Status.SUCCEEDED, {"gears": 2})
    assert (failed.status, failed.error_code) == (Status.FAILED, "files_incomplete")


def test_begin_names_the_import_job_and_its_owner():
    job = _store(MemoryState()).begin(_USER_ID, conflict="held")

    assert (job.kind, job.owner_id, job.subject) == (profile_constants.IMPORT_JOB, _USER_ID, str(_USER_ID))


def test_read_job_returns_the_import_until_a_later_one_replaces_it():
    store = _store(MemoryState())
    first = store.begin(_USER_ID, conflict="held")
    store.set_status(_USER_ID, Status.FAILED, error_code=profile_constants.ImportFailure.INVALID_FILE)
    second = store.begin(_USER_ID, conflict="held")

    assert store.read_job(first) is None
    job, state = store.read_job(second)
    assert job.id == second.id
    assert state.status == Status.QUEUED
