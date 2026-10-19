"""Storage-side sweep for blobs whose activity is gone."""

from time import time
from unittest.mock import MagicMock

import modules.activities.activity_file_storage.files as files
import modules.activities.activity_media.service as media_service
import modules.activities.activity_thumbnail.service as thumbnail_service
import modules.activities.orphan_sweep as orphan_sweep

_OLD = time() - 10 * orphan_sweep.MIN_AGE_SECONDS


def _storage(objects: list[tuple[str, float]]) -> MagicMock:
    storage = MagicMock()
    storage.iter_objects.return_value = iter(objects)
    return storage


def _id_of(key: str) -> int | None:
    return int(key) if key.isdecimal() else None


class TestSweepOrphanedBlobs:
    def test_deletes_only_blobs_whose_activity_is_gone(self):
        storage = _storage([("1", _OLD), ("2", _OLD)])

        removed = orphan_sweep.sweep_orphaned_blobs(storage, "area", lambda ids: {1}, _id_of)

        assert removed == 1
        storage.delete.assert_called_once_with("area", "2")

    def test_skips_blobs_younger_than_the_age_guard(self):
        storage = _storage([("2", time())])

        removed = orphan_sweep.sweep_orphaned_blobs(storage, "area", lambda ids: set(), _id_of)

        assert removed == 0
        storage.delete.assert_not_called()

    def test_leaves_keys_it_does_not_own(self):
        storage = _storage([("not-an-id", _OLD)])

        removed = orphan_sweep.sweep_orphaned_blobs(storage, "area", lambda ids: set(), _id_of)

        assert removed == 0
        storage.delete.assert_not_called()

    def test_empty_area_does_not_query_existence(self):
        lookup = MagicMock()

        assert orphan_sweep.sweep_orphaned_blobs(_storage([]), "area", lookup, _id_of) == 0
        lookup.assert_not_called()


class TestKeyParsers:
    def test_processed_key_names_its_activity(self):
        assert files.activity_id_of_processed_key("processed/42.fit") == 42

    def test_staged_upload_in_the_same_area_is_not_a_retained_file(self):
        assert files.activity_id_of_processed_key("upload_staging/42.fit") is None

    def test_processed_key_with_unknown_extension_is_ignored(self):
        assert files.activity_id_of_processed_key("processed/42.exe") is None

    def test_thumbnail_key(self):
        assert thumbnail_service._activity_id_of_thumbnail_key("7.webp") == 7
        assert thumbnail_service._activity_id_of_thumbnail_key("7.png") is None
        assert thumbnail_service._activity_id_of_thumbnail_key("x.webp") is None

    def test_media_key(self):
        assert media_service._activity_id_of_media_key("7_abc.jpg") == 7
        assert media_service._activity_id_of_media_key("abc.jpg") is None


class TestSweepUnreferencedBlobs:
    def test_deletes_only_old_blobs_no_row_names(self):
        storage = _storage([("1_a.jpg", _OLD), ("1_b.jpg", _OLD), ("1_c.jpg", time())])

        removed = orphan_sweep.sweep_unreferenced_blobs(storage, "area", lambda keys: {"1_a.jpg"})

        assert removed == 1
        storage.delete.assert_called_once_with("area", "1_b.jpg")
