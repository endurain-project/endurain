"""A background job tells its owner's client when it ends, whichever way it ends.

The hint is sent from the state store that records the final status, so no path that ends a job (the job
body, a request that never started it, the dead-letter close) can skip it.
"""

import uuid

import jasil.runtime as jasil_runtime
import jasil.testing as jasil_testing
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

_USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
_SESSION = uuid.UUID(int=601)


@pytest.fixture
def pushes():
    """The hints the platform delivered, in order."""
    return jasil_testing.capture_hints(jasil_runtime.get_active_platform())


def _hint(job_id: uuid.UUID, kind: str) -> tuple[str, dict[str, str]]:
    return f"user:{_USER}", {"message": "JOB_STATUS_CHANGED", "job_id": str(job_id), "kind": kind}


def _sync_cases():
    garmin = garmin_sync_state_store.GarminSyncStateStore(MemoryState())
    strava = strava_sync_state_store.StravaSyncStateStore(MemoryState())
    bulk_edit = bulk_edit_state_store.ActivityBulkEditStateStore(MemoryState())
    return [
        pytest.param(garmin, garmin_constants.SyncKind.GEAR, "garmin_sync_gear", id="garmin-gear"),
        pytest.param(garmin, garmin_constants.SyncKind.HEALTH, "garmin_sync_health", id="garmin-health"),
        pytest.param(strava, strava_constants.SyncKind.GEAR, "strava_gear", id="strava-gear"),
        pytest.param(strava, strava_constants.SyncKind.LINK, "strava_link", id="strava-link"),
        pytest.param(strava, strava_constants.SyncKind.UNLINK, "strava_unlink", id="strava-unlink"),
        pytest.param(bulk_edit, bulk_edit_constants.BulkEditKind.VISIBILITY, "activities_bulk_edit", id="bulk-edit"),
    ]


class TestQueuedSyncs:
    @pytest.mark.parametrize(("states", "kind", "job"), _sync_cases())
    @pytest.mark.parametrize("final", ["succeeded", "failed"])
    def test_a_final_status_is_announced(self, pushes, states, kind, job, final):
        started = states.begin(_USER, kind, conflict="Busy")
        states.set_status(_USER, kind, "running", job_id=started.id)
        assert pushes == []

        states.set_status(_USER, kind, final, job_id=started.id)

        assert pushes == [_hint(started.id, job)]

    @pytest.mark.parametrize(("states", "kind", "job"), _sync_cases())
    def test_closing_a_dead_lettered_sync_is_announced(self, pushes, states, kind, job):
        started = states.begin(_USER, kind, conflict="Busy")

        assert states.close_pending(_USER, kind, job_id=started.id) is True

        assert pushes == [_hint(started.id, job)]

    @pytest.mark.parametrize(("states", "kind", "job"), _sync_cases())
    def test_closing_a_sync_that_already_ended_announces_nothing_more(self, pushes, states, kind, job):
        started = states.begin(_USER, kind, conflict="Busy")
        states.set_status(_USER, kind, "succeeded", job_id=started.id)
        pushes.clear()

        assert states.close_pending(_USER, kind, job_id=started.id) is False

        assert pushes == []


class TestProfileExport:
    def test_a_completed_export_is_announced(self, pushes):
        states = export_state_store.ProfileExportStateStore(MemoryState())
        started = states.begin(_USER, _SESSION, conflict="Busy")
        states.set_status(_USER, started.id, profile_constants.ExportStatus.RUNNING)
        assert pushes == []

        states.set_status(_USER, started.id, profile_constants.ExportStatus.SUCCEEDED, size_bytes=10)

        assert pushes == [_hint(started.id, "profile_export")]

    def test_a_failed_export_is_announced(self, pushes):
        states = export_state_store.ProfileExportStateStore(MemoryState())
        started = states.begin(_USER, _SESSION, conflict="Busy")

        states.set_status(
            _USER,
            started.id,
            profile_constants.ExportStatus.FAILED,
            error_code=profile_constants.ExportFailure.PROCESSING_FAILED,
        )

        assert pushes == [_hint(started.id, "profile_export")]


class TestProfileImport:
    @pytest.mark.parametrize(
        "progress", [profile_constants.ImportStatus.RUNNING, profile_constants.ImportStatus.WRITING_FILES]
    )
    def test_progress_is_not_announced(self, pushes, progress):
        states = import_state_store.ProfileImportStateStore(MemoryState())
        started = states.begin(_USER, conflict="Busy")

        states.set_status(_USER, started.id, progress)

        assert pushes == []

    def test_a_completed_import_is_announced(self, pushes):
        states = import_state_store.ProfileImportStateStore(MemoryState())
        started = states.begin(_USER, conflict="Busy")

        states.set_status(_USER, started.id, profile_constants.ImportStatus.SUCCEEDED, imported={"activities": 1})

        assert pushes == [_hint(started.id, "profile_import")]

    def test_a_failed_import_is_announced(self, pushes):
        states = import_state_store.ProfileImportStateStore(MemoryState())
        started = states.begin(_USER, conflict="Busy")

        states.set_status(
            _USER,
            started.id,
            profile_constants.ImportStatus.FAILED,
            error_code=profile_constants.ImportFailure.PROCESSING_FAILED,
        )

        assert pushes == [_hint(started.id, "profile_import")]
