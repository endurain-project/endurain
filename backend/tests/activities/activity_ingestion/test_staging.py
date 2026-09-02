"""Tests for node-independent bulk-import staging.

Exercised against a real ``LocalStorage`` rather than a mocked provider: the
point of staging is that the bytes survive the hop between the node that
received the file and the worker that imports it, and a mock cannot show that.
"""

import os
from pathlib import Path

import pytest
from jasil.backends.storage_local import LocalStorage

import modules.activities.activity_ingestion.staging as staging


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Point the staging module at a real local storage rooted in tmp_path."""
    backend = LocalStorage(base_dir=str(tmp_path / "storage"), url_prefix="/files")
    monkeypatch.setattr(staging, "_storage", lambda: backend)
    return backend


@pytest.fixture
def dropped(tmp_path):
    """A file in a user's drop directory, as a bulk import starts life."""
    drop_dir = tmp_path / "bulk_import" / "3"
    drop_dir.mkdir(parents=True)
    path = drop_dir / "morning run.gpx"
    path.write_bytes(b"<gpx/>")
    return path


class TestBuildKey:
    def test_is_flat_and_prefixed_with_the_owner(self):
        """The local backend's list_keys does not recurse, so a nested key would
        be invisible to any future orphan sweep."""
        key = staging.build_key(3, "x.gpx")

        assert "/" not in key
        assert key.startswith("3_")

    def test_keeps_the_extension_because_the_pipeline_dispatches_on_it(self):
        assert staging.build_key(3, "X.GPX").endswith(".gpx")

    def test_two_files_of_the_same_name_do_not_collide(self):
        """Re-importing the same filename must not overwrite a queued blob."""
        assert staging.build_key(3, "x.gpx") != staging.build_key(3, "x.gpx")


class TestStageFile:
    def test_moves_the_bytes_into_storage(self, storage, dropped):
        key = staging.stage_file(3, str(dropped))

        assert storage.get(staging.BULK_IMPORT_STORAGE_AREA, key) == b"<gpx/>"

    def test_leaves_the_local_original_in_place(self, storage, dropped):
        """The file is only consumed once the job referencing it is durable.

        Deleting it here would mean a publish failure ate the user's files while
        nothing existed to import them.
        """
        staging.stage_file(3, str(dropped))

        assert dropped.exists()


class TestSettle:
    def test_removes_the_originals_once_the_jobs_are_committed(self, storage, dropped):
        """Otherwise the next scan of the drop directory re-imports them."""
        key = staging.stage_file(3, str(dropped))

        staging.settle([(key, str(dropped))], 3)

        assert not dropped.exists()

    def test_a_failure_to_remove_an_original_is_not_fatal(self, storage, dropped, monkeypatch):
        key = staging.stage_file(3, str(dropped))
        monkeypatch.setattr(staging.os, "remove", lambda _p: (_ for _ in ()).throw(OSError("read-only")))

        staging.settle([(key, str(dropped))], 3)

        assert storage.get(staging.BULK_IMPORT_STORAGE_AREA, key) == b"<gpx/>"


class TestUnstage:
    def test_drops_blobs_whose_jobs_were_never_published(self, storage, dropped):
        key = staging.stage_file(3, str(dropped))

        staging.unstage([key])

        assert storage.get(staging.BULK_IMPORT_STORAGE_AREA, key) is None
        # The user's file is untouched, so they can simply retry.
        assert dropped.exists()

    def test_a_delete_failure_is_logged_not_raised(self, storage, monkeypatch):
        monkeypatch.setattr(storage, "delete", lambda *_a, **_k: (_ for _ in ()).throw(OSError("gone")))

        staging.unstage(["3_abc.gpx"])


class TestMaterialized:
    def test_writes_the_blob_under_its_original_name(self, storage):
        """The pipeline reads meaning from the filename: the Strava export's
        activities.csv is keyed by it."""
        storage.save(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx", b"<gpx/>")

        with staging.materialized("3_abc.gpx", "morning run.gpx") as path:
            assert os.path.basename(path) == "morning run.gpx"
            assert Path(path).read_bytes() == b"<gpx/>"

    def test_cleans_up_afterwards(self, storage):
        storage.save(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx", b"<gpx/>")

        with staging.materialized("3_abc.gpx", "x.gpx") as path:
            captured = path

        assert not Path(captured).exists()

    def test_yields_none_when_the_blob_is_gone(self, storage):
        with staging.materialized("3_missing.gpx", "x.gpx") as path:
            assert path is None

    def test_a_traversing_filename_cannot_escape_the_temp_directory(self, storage):
        """The name arrives in a durable payload the worker trusts."""
        storage.save(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx", b"<gpx/>")

        with staging.materialized("3_abc.gpx", "../../etc/passwd") as path:
            assert os.path.basename(path) == "passwd"
            assert "etc" not in Path(path).parent.parts


class TestDiscard:
    def test_removes_the_staged_blob(self, storage):
        storage.save(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx", b"<gpx/>")

        staging.discard("3_abc.gpx")

        assert storage.get(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx") is None


class TestMoveToErrors:
    def test_moves_the_blob_to_the_error_area(self, storage):
        storage.save(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx", b"<gpx/>")

        staging.move_to_errors("3_abc.gpx", 3, "x.gpx")

        assert storage.get(staging.BULK_IMPORT_ERROR_STORAGE_AREA, "3_abc.gpx") == b"<gpx/>"
        assert storage.get(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx") is None

    def test_a_missing_blob_is_logged_not_raised(self, storage):
        """Raising here would mask the import error that caused the dead-letter."""
        staging.move_to_errors("3_missing.gpx", 3, "x.gpx")

        assert storage.get(staging.BULK_IMPORT_ERROR_STORAGE_AREA, "3_missing.gpx") is None

    def test_a_storage_failure_is_logged_not_raised(self, storage, monkeypatch):
        storage.save(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx", b"<gpx/>")
        monkeypatch.setattr(storage, "save", lambda *_a, **_k: (_ for _ in ()).throw(OSError("full")))

        staging.move_to_errors("3_abc.gpx", 3, "x.gpx")

        assert storage.get(staging.BULK_IMPORT_STORAGE_AREA, "3_abc.gpx") == b"<gpx/>"
