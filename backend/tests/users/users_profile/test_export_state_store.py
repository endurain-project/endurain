"""Tests for users_profile.export_state_store (provider-backed)."""

from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_state_store as export_state_store

Status = profile_constants.ExportStatus


def test_begin_records_queued_and_refuses_a_second_export():
    store = export_state_store.ProfileExportStateStore(MemoryState())

    assert store.begin(1) is True
    assert store.get(1) == export_state_store.ProfileExportState(status=Status.QUEUED)
    assert store.begin(1) is False
    assert store.begin(2) is True


def test_a_finished_export_releases_the_claim_and_keeps_its_size():
    store = export_state_store.ProfileExportStateStore(MemoryState())
    store.begin(1)

    store.set_status(1, Status.COMPLETED, size_bytes=12)

    assert store.get(1).size_bytes == 12
    assert store.begin(1) is True


def test_state_lives_under_the_users_namespace():
    state = MemoryState()
    export_state_store.ProfileExportStateStore(state).begin(5)

    assert state.get(core_attempt_state.key("users", "profile_export:state", "5")) is not None
