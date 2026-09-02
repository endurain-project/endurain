"""Tests for the activity_file_storage service (storage-backed source files)."""

from jasil.backends.storage_local import LocalStorage

import modules.activities.activity_file_storage.service as service


class TestActivityFileKey:
    def test_adds_dot_and_lowercases(self):
        assert service.activity_file_key(42, "fit") == "42.fit"
        assert service.activity_file_key(42, ".FIT") == "42.fit"
        assert service.activity_file_key(7, ".gpx") == "7.gpx"


class TestStoreAndGet:
    def test_store_then_get_round_trips(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        key = service.store_activity_file(42, ".fit", b"fitbytes", storage)
        assert key == "42.fit"
        assert service.get_activity_file(42, storage) == ("42.fit", b"fitbytes")

    def test_get_returns_none_when_missing(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        assert service.get_activity_file(99, storage) is None

    def test_store_for_ids_writes_each(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        service.store_activity_file_for_ids([1, 2, 3], ".gpx", b"data", storage)
        for activity_id in (1, 2, 3):
            assert service.get_activity_file(activity_id, storage) == (f"{activity_id}.gpx", b"data")

    def test_get_probes_known_extensions(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        service.store_activity_file(5, ".tcx", b"tcx", storage)
        assert service.get_activity_file(5, storage) == ("5.tcx", b"tcx")

    def test_storage_area_coincides_with_processed_dir_layout(self, tmp_path):
        # The local area maps to {DATA_DIR}/activity_files/processed, the exact
        # directory files used to be moved into, so existing self-host installs
        # need no data migration.
        storage = LocalStorage(str(tmp_path))
        service.store_activity_file(1, ".gpx", b"data", storage)
        assert (tmp_path / "activity_files" / "processed" / "1.gpx").is_file()


class TestDelete:
    def test_delete_removes_stored_file(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        service.store_activity_file(42, ".fit", b"x", storage)
        service.delete_activity_file(42, storage)
        assert service.get_activity_file(42, storage) is None

    def test_delete_is_idempotent_when_absent(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        # Must not raise even though nothing is stored.
        service.delete_activity_file(123, storage)
        assert service.get_activity_file(123, storage) is None
