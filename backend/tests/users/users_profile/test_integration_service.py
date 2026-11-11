"""Tests for the users_profile module surface."""

from unittest.mock import MagicMock, patch

from jasil.backends.state_memory import MemoryState

import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_state_store as export_state_store
import modules.users.users_profile.import_state_store as import_state_store
import modules.users.users_profile.integration_service as profile_integration

_MODULE = "modules.users.users_profile.integration_service"


def test_deleting_staged_transfers_discards_the_export_and_the_imports():
    storage = MagicMock()

    with (
        patch(f"{_MODULE}.profile_export_job_service.discard_staged_export") as export,
        patch(f"{_MODULE}.profile_import_job_service.discard_staged_imports") as imports,
    ):
        profile_integration.delete_staged_transfers(7, storage)

    export.assert_called_once_with(7, storage)
    imports.assert_called_once_with(7, storage)


def test_shutdown_stops_the_transfer_pool():
    with patch("modules.users.users_profile.integration_service.profile_transfer_pool.pool") as pool:
        profile_integration.shutdown_transfer_pool()

    pool.shutdown.assert_called_once_with()


def _begin_export(state, user_id=1):

    return export_state_store.ProfileExportStateStore(state).begin(user_id, conflict="held")


def _begin_import(state, user_id=1):

    return import_state_store.ProfileImportStateStore(state).begin(user_id, conflict="held")


def test_read_export_job_returns_the_current_export_with_its_id_and_kind():
    state = MemoryState()
    job = _begin_export(state)

    status = profile_integration.read_export_job(job, state)

    assert (status.id, status.kind, status.status) == (job.id, "profile_export", "queued")


def test_read_export_job_is_none_for_an_earlier_job_and_once_expired():
    state = MemoryState()
    first = _begin_export(state)

    export_state_store.ProfileExportStateStore(state).set_status(1, profile_constants.ExportStatus.FAILED)
    _begin_export(state)
    assert profile_integration.read_export_job(first, state) is None

    assert profile_integration.read_export_job(first, MemoryState()) is None


def test_read_import_job_returns_the_current_import_with_its_id_and_kind():
    state = MemoryState()
    job = _begin_import(state)

    status = profile_integration.read_import_job(job, state)

    assert (status.id, status.kind, status.status) == (job.id, "profile_import", "queued")


def test_read_import_job_is_none_for_an_earlier_job_and_once_expired():

    state = MemoryState()
    first = _begin_import(state)
    import_state_store.ProfileImportStateStore(state).set_status(1, profile_constants.ImportStatus.FAILED)
    _begin_import(state)
    assert profile_integration.read_import_job(first, state) is None

    assert profile_integration.read_import_job(first, MemoryState()) is None
