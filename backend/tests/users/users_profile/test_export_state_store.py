"""Tests for users_profile.export_state_store (provider-backed)."""

from datetime import UTC, datetime, timedelta

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


def test_a_completed_export_records_when_its_download_stops_working():
    store = export_state_store.ProfileExportStateStore(MemoryState(), ttl_seconds=600)
    store.begin(1)
    before = datetime.now(UTC)

    store.set_status(1, Status.COMPLETED, size_bytes=12)

    expires_at = store.get(1).expires_at
    assert expires_at.tzinfo is not None
    assert before + timedelta(seconds=600) <= expires_at <= datetime.now(UTC) + timedelta(seconds=600)


def test_an_export_that_is_not_downloadable_has_no_expiry():
    store = export_state_store.ProfileExportStateStore(MemoryState())
    store.begin(1)
    assert store.get(1).expires_at is None
    store.set_status(1, Status.FAILED, failure=profile_constants.ExportFailure.TIMED_OUT)
    assert store.get(1).expires_at is None
    assert store.get(2) is None


def test_a_state_written_before_expires_at_existed_still_reads():
    state = MemoryState()
    state.set(
        core_attempt_state.key("users", "profile_export:state", "1"),
        b'{"status":"completed","failure":null,"size_bytes":5}',
        ttl_seconds=60,
    )

    read = export_state_store.ProfileExportStateStore(state).get(1)

    assert (read.status, read.size_bytes, read.expires_at) == (Status.COMPLETED, 5, None)
