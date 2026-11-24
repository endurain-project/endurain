"""The profile surface other modules call: staged transfers, the transfer pool and the job reads."""

import threading
import uuid

import pytest

import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_state_store as export_state_store
import modules.users.users_profile.import_state_store as import_state_store
import modules.users.users_profile.integration_service as profile_integration
import modules.users.users_profile.transfer_pool as transfer_pool
from tests._helpers.clock import memory_state

_SESSION = uuid.UUID(int=601)


@pytest.fixture
def platform(_publish_local_platform):
    return _publish_local_platform


def test_deleting_staged_transfers_discards_the_export_and_the_imports_of_that_user_only(platform):
    storage, mine, theirs = platform.storage, uuid.uuid4(), uuid.uuid4()
    for user_id in (mine, theirs):
        storage.save(profile_constants.EXPORT_STAGING_AREA, profile_constants.export_staged_key(user_id), b"zip")
        storage.save(profile_constants.IMPORT_STAGING_AREA, f"{user_id}/a.zip", b"zip")

    profile_integration.delete_staged_transfers(mine, storage)

    assert storage.list_keys(profile_constants.EXPORT_STAGING_AREA, "") == [profile_constants.export_staged_key(theirs)]
    assert storage.list_keys(profile_constants.IMPORT_STAGING_AREA, "") == [f"{theirs}/a.zip"]


def test_shutdown_stops_the_transfer_pool_and_a_later_job_starts_it_again():
    ran = []
    transfer_pool.pool.submit(ran.append, "first").result(timeout=30)

    profile_integration.shutdown_transfer_pool()
    transfer_pool.pool.submit(ran.append, "second").result(timeout=30)

    assert ran == ["first", "second"]
    transfer_pool.pool.shutdown(wait=True)


def test_shutdown_drops_the_jobs_still_queued():
    release, ran = threading.Event(), []
    transfer_pool.pool.submit(release.wait)
    queued = transfer_pool.pool.submit(ran.append, "never")

    profile_integration.shutdown_transfer_pool()
    release.set()

    assert queued.cancelled()
    assert ran == []


class TestReadJobs:
    def test_the_current_export_is_read_with_its_id_and_kind(self, platform):
        user_id = uuid.uuid4()
        states = export_state_store.ProfileExportStateStore(platform.state)
        job = states.begin(user_id, _SESSION, conflict="held")

        status = profile_integration.read_export_job(job, platform.state)

        assert status is not None
        assert (status.id, status.kind, status.status) == (job.id, profile_constants.EXPORT_JOB, "queued")

    def test_an_export_is_none_for_an_earlier_job_and_once_gone(self, platform):
        user_id = uuid.uuid4()
        states = export_state_store.ProfileExportStateStore(platform.state)
        first = states.begin(user_id, _SESSION, conflict="held")
        states.set_status(user_id, first.id, profile_constants.ExportStatus.FAILED)
        second = states.begin(user_id, _SESSION, conflict="held")

        assert profile_integration.read_export_job(first, platform.state) is None
        assert profile_integration.read_export_job(second, platform.state) is not None
        assert profile_integration.read_export_job(second, memory_state()) is None

    def test_the_current_import_is_read_with_its_id_and_kind(self, platform):
        user_id = uuid.uuid4()
        states = import_state_store.ProfileImportStateStore(platform.state)
        job = states.begin(user_id, conflict="held")

        status = profile_integration.read_import_job(job, platform.state)

        assert status is not None
        assert (status.id, status.kind, status.status) == (job.id, profile_constants.IMPORT_JOB, "queued")

    def test_an_import_is_none_for_an_earlier_job_and_once_gone(self, platform):
        user_id = uuid.uuid4()
        states = import_state_store.ProfileImportStateStore(platform.state)
        first = states.begin(user_id, conflict="held")
        states.set_status(user_id, first.id, profile_constants.ImportStatus.FAILED)
        second = states.begin(user_id, conflict="held")

        assert profile_integration.read_import_job(first, platform.state) is None
        assert profile_integration.read_import_job(second, platform.state) is not None
        assert profile_integration.read_import_job(second, memory_state()) is None
