"""Tests for the activity_file_storage integration service (storage-backed source files)."""

import os
import time
from unittest.mock import patch

from jasil.backends.storage_local import LocalStorage

import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_file_storage.scheduled_jobs as activity_file_storage_scheduled_jobs

AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA


def _plain_storage(root) -> LocalStorage:
    """A local backend configured the way the application configures it."""
    return LocalStorage(str(root), plain_areas=frozenset({AREA}))


def _age(path, seconds: int) -> None:
    """Backdate a file so the orphan sweep's age guard lets it through."""
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


class TestActivityFileKey:
    def test_adds_dot_and_lowercases(self):
        assert activity_file_storage_files.activity_file_key(42, "fit") == "42.fit"
        assert activity_file_storage_files.activity_file_key(42, ".FIT") == "42.fit"
        assert activity_file_storage_files.activity_file_key(7, ".gpx") == "7.gpx"


class TestStoreAndGet:
    def test_store_then_get_round_trips(self, tmp_path):
        storage = _plain_storage(tmp_path)
        key = activity_file_storage_integration.store_activity_file(42, ".fit", b"fitbytes", storage)
        assert key == "42.fit"
        assert activity_file_storage_integration.get_activity_file(42, storage) == ("42.fit", b"fitbytes")

    def test_store_writes_a_browsable_file(self, tmp_path):
        activity_file_storage_integration.store_activity_file(42, ".fit", b"fitbytes", _plain_storage(tmp_path))

        assert (tmp_path / "activity_files" / "processed" / "42.fit").read_bytes() == b"fitbytes"

    def test_get_returns_none_when_missing(self, tmp_path):
        storage = _plain_storage(tmp_path)
        assert activity_file_storage_integration.get_activity_file(99, storage) is None

    def test_store_for_ids_writes_each(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file_for_ids([1, 2, 3], ".gpx", b"data", storage)
        for activity_id in (1, 2, 3):
            assert activity_file_storage_integration.get_activity_file(activity_id, storage) == (
                f"{activity_id}.gpx",
                b"data",
            )

    def test_get_probes_known_extensions(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file(5, ".tcx", b"tcx", storage)
        assert activity_file_storage_integration.get_activity_file(5, storage) == ("5.tcx", b"tcx")

    def test_reads_files_already_at_the_plain_processed_path(self, tmp_path):
        legacy_file = tmp_path / "activity_files" / "processed" / "1.gpx"
        legacy_file.parent.mkdir(parents=True)
        legacy_file.write_bytes(b"legacy")

        assert activity_file_storage_integration.get_activity_file(1, _plain_storage(tmp_path)) == ("1.gpx", b"legacy")

    def test_reads_a_file_still_in_the_opaque_layout(self, tmp_path):
        # Written by a release that stored the area in JASIL's private layout.
        activity_file_storage_integration.store_activity_file(7, ".fit", b"opaque", LocalStorage(str(tmp_path)))

        assert activity_file_storage_integration.get_activity_file(7, _plain_storage(tmp_path)) == ("7.fit", b"opaque")

    def test_overwriting_moves_the_opaque_copy_to_the_plain_path(self, tmp_path):
        activity_file_storage_integration.store_activity_file(7, ".fit", b"opaque", LocalStorage(str(tmp_path)))

        activity_file_storage_integration.store_activity_file(7, ".fit", b"plain", _plain_storage(tmp_path))

        assert (tmp_path / "activity_files" / "processed" / "7.fit").read_bytes() == b"plain"
        assert list((tmp_path / ".jasil-objects").rglob("object")) == []


class TestDelete:
    def test_delete_removes_stored_file(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file(42, ".fit", b"x", storage)
        activity_file_storage_files.delete_activity_file(42, storage)
        assert activity_file_storage_integration.get_activity_file(42, storage) is None

    def test_delete_removes_a_file_left_in_the_opaque_layout(self, tmp_path):
        activity_file_storage_integration.store_activity_file(7, ".fit", b"opaque", LocalStorage(str(tmp_path)))

        activity_file_storage_files.delete_activity_file(7, _plain_storage(tmp_path))

        assert list((tmp_path / ".jasil-objects").rglob("object")) == []

    def test_delete_is_idempotent_when_absent(self, tmp_path):
        storage = _plain_storage(tmp_path)
        # Must not raise even though nothing is stored.
        activity_file_storage_files.delete_activity_file(123, storage)
        assert activity_file_storage_integration.get_activity_file(123, storage) is None


class TestOrphanSweepOnPlainLayout:
    def test_deletes_orphans_and_leaves_the_shared_directory_alone(self, tmp_path):
        storage = _plain_storage(tmp_path)
        activity_file_storage_integration.store_activity_file(1, ".fit", b"alive", storage)
        activity_file_storage_integration.store_activity_file(2, ".fit", b"orphan", storage)
        storage.save(AREA, "upload_staging/staged.fit", b"staged")
        bulk_upload = tmp_path / "activity_files" / "bulk_import" / "1" / "drop.fit"
        bulk_upload.parent.mkdir(parents=True)
        bulk_upload.write_bytes(b"bulk")
        for path in (
            tmp_path / "activity_files" / "processed" / "2.fit",
            tmp_path / "activity_files" / "upload_staging" / "staged.fit",
            bulk_upload,
        ):
            _age(path, 2 * 3600)

        with (
            patch("modules.activities.activity_file_storage.scheduled_jobs.platform_runtime") as runtime,
            patch("core.blob_sweep.core_database"),
            patch("modules.activities.activity_file_storage.scheduled_jobs.activity_integration") as integration,
        ):
            runtime.get_active_platform.return_value.storage = storage
            integration.filter_existing_activity_ids.return_value = {1}

            activity_file_storage_scheduled_jobs.sweep_orphaned_activity_files()

        assert not (tmp_path / "activity_files" / "processed" / "2.fit").exists()
        assert (tmp_path / "activity_files" / "processed" / "1.fit").exists()
        assert (tmp_path / "activity_files" / "upload_staging" / "staged.fit").exists()
        assert bulk_upload.exists()
