"""Tests for the activity_file_storage integration service (storage-backed source files)."""

import uuid

from jasil.backends.storage_local import LocalStorage

import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_file_storage.scheduled_jobs as activity_file_storage_scheduled_jobs
from tests._factories.activities import make_activity
from tests._factories.ingestion import age_stored_objects
from tests._factories.users import make_user

AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA

ID_1 = uuid.UUID("00000000-0000-4000-8000-000000000001")
ID_2 = uuid.UUID("00000000-0000-4000-8000-000000000002")
ID_3 = uuid.UUID("00000000-0000-4000-8000-000000000003")
ID_5 = uuid.UUID("00000000-0000-4000-8000-000000000005")
ID_7 = uuid.UUID("00000000-0000-4000-8000-000000000007")
ID_42 = uuid.UUID("00000000-0000-4000-8000-000000000042")
ID_99 = uuid.UUID("00000000-0000-4000-8000-000000000099")
ID_123 = uuid.UUID("00000000-0000-4000-8000-000000000123")


def _plain_storage(root) -> LocalStorage:
    """A local backend configured the way the application configures it."""
    return LocalStorage(str(root), plain_areas=frozenset({AREA}))


class TestActivityFileKey:
    def test_adds_dot_and_lowercases(self):
        assert activity_file_storage_files.activity_file_key(ID_42, "fit") == f"{ID_42}.fit"
        assert activity_file_storage_files.activity_file_key(ID_42, ".FIT") == f"{ID_42}.fit"
        assert activity_file_storage_files.activity_file_key(ID_7, ".gpx") == f"{ID_7}.gpx"


class TestStoreAndGet:
    def test_store_then_get_round_trips(self, tmp_path):
        storage = _plain_storage(tmp_path)
        key = activity_file_storage_integration.store_activity_file(ID_42, ".fit", b"fitbytes", storage)
        assert key == f"{ID_42}.fit"
        assert activity_file_storage_integration.get_activity_file(ID_42, storage) == (f"{ID_42}.fit", b"fitbytes")

    def test_store_writes_a_browsable_file(self, tmp_path):
        activity_file_storage_integration.store_activity_file(ID_42, ".fit", b"fitbytes", _plain_storage(tmp_path))

        assert (tmp_path / "activity_files" / "processed" / f"{ID_42}.fit").read_bytes() == b"fitbytes"

    def test_get_returns_none_when_missing(self, tmp_path):
        storage = _plain_storage(tmp_path)
        assert activity_file_storage_integration.get_activity_file(ID_99, storage) is None

    def test_store_for_ids_writes_each(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file_for_ids([ID_1, ID_2, ID_3], ".gpx", b"data", storage)
        for activity_id in (ID_1, ID_2, ID_3):
            assert activity_file_storage_integration.get_activity_file(activity_id, storage) == (
                f"{activity_id}.gpx",
                b"data",
            )

    def test_get_probes_known_extensions(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file(ID_5, ".tcx", b"tcx", storage)
        assert activity_file_storage_integration.get_activity_file(ID_5, storage) == (f"{ID_5}.tcx", b"tcx")

    def test_reads_files_already_at_the_plain_processed_path(self, tmp_path):
        plain_file = tmp_path / "activity_files" / "processed" / f"{ID_1}.gpx"
        plain_file.parent.mkdir(parents=True)
        plain_file.write_bytes(b"plain")

        assert activity_file_storage_integration.get_activity_file(ID_1, _plain_storage(tmp_path)) == (
            f"{ID_1}.gpx",
            b"plain",
        )


class TestDelete:
    def test_delete_removes_stored_file(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file(ID_42, ".fit", b"x", storage)
        activity_file_storage_files.delete_activity_file(ID_42, storage)
        assert activity_file_storage_integration.get_activity_file(ID_42, storage) is None

    def test_delete_removes_a_file_left_in_the_opaque_layout(self, tmp_path):
        activity_file_storage_integration.store_activity_file(ID_7, ".fit", b"opaque", LocalStorage(str(tmp_path)))

        activity_file_storage_files.delete_activity_file(ID_7, _plain_storage(tmp_path))

        assert list((tmp_path / ".jasil-objects").rglob("object")) == []

    def test_delete_is_idempotent_when_absent(self, tmp_path):
        storage = _plain_storage(tmp_path)
        # Must not raise even though nothing is stored.
        activity_file_storage_files.delete_activity_file(ID_123, storage)
        assert activity_file_storage_integration.get_activity_file(ID_123, storage) is None


class TestOrphanSweep:
    def test_deletes_the_files_of_activities_that_are_gone_and_leaves_everything_else(
        self, storage, committed_sessions, tmp_path
    ):
        with committed_sessions() as db:
            alive = make_activity(db, make_user(db).id)
            db.commit()
        orphan = uuid.uuid4()
        activity_file_storage_integration.store_activity_file(alive.id, ".fit", b"alive", storage)
        activity_file_storage_integration.store_activity_file(orphan, ".fit", b"orphan", storage)
        storage.save(AREA, "upload_staging/staged.fit", b"staged")
        storage.save(AREA, "processed/42.fit", b"integer layout")
        age_stored_objects(tmp_path, 2 * 3600)
        recent_orphan = uuid.uuid4()
        activity_file_storage_integration.store_activity_file(recent_orphan, ".fit", b"just written", storage)

        activity_file_storage_scheduled_jobs.sweep_orphaned_activity_files()

        assert activity_file_storage_integration.get_activity_file(orphan, storage) is None
        assert activity_file_storage_integration.get_activity_file(alive.id, storage) is not None
        assert activity_file_storage_integration.get_activity_file(recent_orphan, storage) is not None, (
            "a file written moments ago may belong to a row that has not committed yet"
        )
        assert storage.get(AREA, "upload_staging/staged.fit") == b"staged"
        assert storage.get(AREA, "processed/42.fit") == b"integer layout"
