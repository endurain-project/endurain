"""Tests for users_profile.export_state_store (provider-backed)."""

from datetime import UTC, datetime, timedelta

import pytest
from jasil.backends.state_memory import MemoryState

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_state_store as export_state_store

Status = profile_constants.ExportStatus


def test_begin_records_queued_and_refuses_a_second_export():
    store = export_state_store.ProfileExportStateStore(MemoryState())

    store.begin(1, conflict="held")
    assert store.get(1) == export_state_store.ProfileExportState(status=Status.QUEUED)
    with pytest.raises(core_exceptions.JobAlreadyRunningError):
        store.begin(1, conflict="held")
    store.begin(2, conflict="held")


def test_a_finished_export_releases_the_claim_and_keeps_its_size():
    store = export_state_store.ProfileExportStateStore(MemoryState())
    store.begin(1, conflict="held")

    store.set_status(1, Status.SUCCEEDED, size_bytes=12)

    assert store.get(1).size_bytes == 12
    store.begin(1, conflict="held")


def test_state_lives_under_the_users_namespace():
    state = MemoryState()
    export_state_store.ProfileExportStateStore(state).begin(5, conflict="held")

    assert state.get(core_attempt_state.key("users", "profile_export:state", "5")) is not None


def test_a_completed_export_records_when_its_download_stops_working():
    store = export_state_store.ProfileExportStateStore(MemoryState(), ttl_seconds=600)
    store.begin(1, conflict="held")
    before = datetime.now(UTC)

    store.set_status(1, Status.SUCCEEDED, size_bytes=12)

    expires_at = store.get(1).expires_at
    assert expires_at.tzinfo is not None
    assert before + timedelta(seconds=600) <= expires_at <= datetime.now(UTC) + timedelta(seconds=600)


def test_an_export_that_is_not_downloadable_has_no_expiry():
    store = export_state_store.ProfileExportStateStore(MemoryState())
    store.begin(1, conflict="held")
    assert store.get(1).expires_at is None
    store.set_status(1, Status.FAILED, error_code=profile_constants.ExportFailure.TIMED_OUT)
    assert store.get(1).expires_at is None
    assert store.get(2) is None


def test_a_state_written_before_expires_at_existed_still_reads():
    read = export_state_store.ProfileExportState.model_validate_json(
        b'{"status":"succeeded","error_code":null,"size_bytes":5}'
    )

    assert (read.status, read.size_bytes, read.expires_at) == (Status.SUCCEEDED, 5, None)


def test_begin_names_the_export_job_and_its_owner():
    job = export_state_store.ProfileExportStateStore(MemoryState()).begin(3, conflict="held")

    assert (job.kind, job.owner_id, job.subject) == (profile_constants.EXPORT_JOB, 3, "3")


def test_read_job_returns_the_export_until_a_later_one_replaces_it():
    store = export_state_store.ProfileExportStateStore(MemoryState())
    first = store.begin(1, conflict="held")
    store.set_status(1, Status.SUCCEEDED, size_bytes=4)
    second = store.begin(1, conflict="held")

    assert store.read_job(first) is None
    job, state = store.read_job(second)
    assert job.id == second.id
    assert state.status == Status.QUEUED


def test_an_export_state_stored_with_the_old_names_reads_as_the_new_ones():
    state = export_state_store.ProfileExportState.model_validate_json(
        b'{"status":"completed","failure":null,"size_bytes":5}'
    )
    failed = export_state_store.ProfileExportState.model_validate_json(b'{"status":"failed","failure":"timed_out"}')

    assert (state.status, state.size_bytes) == (Status.SUCCEEDED, 5)
    assert (failed.status, failed.error_code) == (Status.FAILED, "timed_out")
