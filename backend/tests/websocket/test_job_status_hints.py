"""A background job tells its owner's client when it ends, whichever way it ends.

The hint is sent from the state store that records the final status, so no path that ends a job (the job
body, a request that never started it, the dead-letter close) can skip it.
"""

from unittest.mock import patch

import pytest
from jasil.backends.state_memory import MemoryState

import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.garmin.constants as garmin_constants
import modules.garmin.sync_state_store as garmin_sync_state_store
import modules.strava.constants as strava_constants
import modules.strava.sync_state_store as strava_sync_state_store
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_state_store as export_state_store
import modules.users.users_profile.import_state_store as import_state_store
import modules.websocket.integration_service as websocket_integration

_USER = 7


@pytest.fixture
def pushes():
    with patch.object(websocket_integration, "push_to_user") as push:
        yield push


def _hint(job: str) -> tuple[int, dict[str, str]]:
    return _USER, {"message": "JOB_STATUS_CHANGED", "job": job}


def _sync_cases():
    garmin = garmin_sync_state_store.GarminSyncStateStore(MemoryState())
    strava = strava_sync_state_store.StravaSyncStateStore(MemoryState())
    bulk_edit = bulk_edit_state_store.ActivityBulkEditStateStore(MemoryState())
    return [
        pytest.param(garmin, garmin_constants.SyncKind.GEAR, "garmin:gear", id="garmin-gear"),
        pytest.param(garmin, garmin_constants.SyncKind.HEALTH, "garmin:health", id="garmin-health"),
        pytest.param(strava, strava_constants.SyncKind.GEAR, "strava:gear", id="strava-gear"),
        pytest.param(strava, strava_constants.SyncKind.LINK, "strava:link", id="strava-link"),
        pytest.param(strava, strava_constants.SyncKind.UNLINK, "strava:unlink", id="strava-unlink"),
        pytest.param(bulk_edit, bulk_edit_constants.BulkEditKind.VISIBILITY, "activities:bulk-edit", id="bulk-edit"),
    ]


class TestQueuedSyncs:
    @pytest.mark.parametrize(("states", "kind", "job"), _sync_cases())
    @pytest.mark.parametrize("final", ["succeeded", "failed"])
    def test_a_final_status_is_announced(self, pushes, states, kind, job, final):
        states.begin(_USER, kind)
        states.set_status(_USER, kind, "running")
        pushes.assert_not_called()

        states.set_status(_USER, kind, final)

        pushes.assert_called_once_with(*_hint(job))

    @pytest.mark.parametrize(("states", "kind", "job"), _sync_cases())
    def test_closing_a_dead_lettered_sync_is_announced(self, pushes, states, kind, job):
        states.begin(_USER, kind)

        assert states.close_pending(_USER, kind) is True

        pushes.assert_called_once_with(*_hint(job))

    @pytest.mark.parametrize(("states", "kind", "job"), _sync_cases())
    def test_closing_a_sync_that_already_ended_announces_nothing_more(self, pushes, states, kind, job):
        states.begin(_USER, kind)
        states.set_status(_USER, kind, "succeeded")
        pushes.reset_mock()

        assert states.close_pending(_USER, kind) is False

        pushes.assert_not_called()


class TestProfileExport:
    def test_a_completed_export_is_announced(self, pushes):
        states = export_state_store.ProfileExportStateStore(MemoryState())
        states.begin(_USER)
        states.set_status(_USER, profile_constants.ExportStatus.RUNNING)
        pushes.assert_not_called()

        states.set_status(_USER, profile_constants.ExportStatus.SUCCEEDED, size_bytes=10)

        pushes.assert_called_once_with(*_hint("profile:export"))

    def test_a_failed_export_is_announced(self, pushes):
        states = export_state_store.ProfileExportStateStore(MemoryState())
        states.begin(_USER)

        states.set_status(
            _USER, profile_constants.ExportStatus.FAILED, error_code=profile_constants.ExportFailure.PROCESSING_FAILED
        )

        pushes.assert_called_once_with(*_hint("profile:export"))


class TestProfileImport:
    @pytest.mark.parametrize(
        "progress", [profile_constants.ImportStatus.RUNNING, profile_constants.ImportStatus.WRITING_FILES]
    )
    def test_progress_is_not_announced(self, pushes, progress):
        states = import_state_store.ProfileImportStateStore(MemoryState())
        states.begin(_USER)

        states.set_status(_USER, progress)

        pushes.assert_not_called()

    def test_a_completed_import_is_announced(self, pushes):
        states = import_state_store.ProfileImportStateStore(MemoryState())
        states.begin(_USER)

        states.set_status(_USER, profile_constants.ImportStatus.SUCCEEDED, imported={"activities": 1})

        pushes.assert_called_once_with(*_hint("profile:import"))

    def test_a_failed_import_is_announced(self, pushes):
        states = import_state_store.ProfileImportStateStore(MemoryState())
        states.begin(_USER)

        states.set_status(
            _USER, profile_constants.ImportStatus.FAILED, error_code=profile_constants.ImportFailure.PROCESSING_FAILED
        )

        pushes.assert_called_once_with(*_hint("profile:import"))
