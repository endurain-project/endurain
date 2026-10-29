"""Storage-side sweeps for blobs no row owns or names."""

from time import time
from unittest.mock import MagicMock, patch

import pytest

import core.blob_sweep as blob_sweep

_OLD = time() - 10 * blob_sweep.MIN_AGE_SECONDS


class _Sessions:
    """Stands in for ``SessionLocal`` and counts the sessions open at any moment."""

    def __init__(self) -> None:
        self.open = 0
        self.opened = 0

    def __call__(self):
        sessions = self

        class _Session:
            def __enter__(self):
                sessions.open += 1
                sessions.opened += 1
                return MagicMock()

            def __exit__(self, *exc):
                sessions.open -= 1

        return _Session()


@pytest.fixture(autouse=True)
def sessions():
    tracker = _Sessions()
    with patch.object(blob_sweep.core_database, "SessionLocal", tracker):
        yield tracker


def _storage(objects: list[tuple[str, float]]) -> MagicMock:
    storage = MagicMock()
    storage.iter_objects.return_value = iter(objects)
    return storage


def _id_of(key: str) -> int | None:
    return int(key) if key.isdecimal() else None


class TestSweepOrphanedBlobs:
    def test_deletes_only_blobs_whose_owner_is_gone(self):
        storage = _storage([("1", _OLD), ("2", _OLD)])

        removed = blob_sweep.sweep_orphaned_blobs(storage, "area", lambda ids, db: {1}, _id_of)

        assert removed == 1
        storage.delete.assert_called_once_with("area", "2")

    def test_skips_blobs_younger_than_the_age_guard(self):
        storage = _storage([("2", time())])

        removed = blob_sweep.sweep_orphaned_blobs(storage, "area", lambda ids, db: set(), _id_of)

        assert removed == 0
        storage.delete.assert_not_called()

    def test_leaves_keys_it_does_not_own(self):
        storage = _storage([("not-an-id", _OLD)])

        removed = blob_sweep.sweep_orphaned_blobs(storage, "area", lambda ids, db: set(), _id_of)

        assert removed == 0
        storage.delete.assert_not_called()

    def test_empty_area_does_not_query_existence(self):
        lookup = MagicMock()

        assert blob_sweep.sweep_orphaned_blobs(_storage([]), "area", lookup, _id_of) == 0
        lookup.assert_not_called()


class TestSweepUnreferencedBlobs:
    def test_deletes_only_old_blobs_no_row_names(self):
        storage = _storage([("1_a.jpg", _OLD), ("1_b.jpg", _OLD), ("1_c.jpg", time())])

        removed = blob_sweep.sweep_unreferenced_blobs(storage, "area", lambda keys, db: {"1_a.jpg"})

        assert removed == 1
        storage.delete.assert_called_once_with("area", "1_b.jpg")


class TestNoSessionAcrossStorageCalls:
    """A storage call on object storage is a network round trip, so no connection may wait on it."""

    @staticmethod
    def _watching_storage(objects, sessions):
        def iter_objects(area, prefix):
            for item in objects:
                assert sessions.open == 0, "a session was open while the storage listing was read"
                yield item

        def delete(area, key):
            assert sessions.open == 0, "a session was open while a blob was deleted"

        storage = MagicMock()
        storage.iter_objects.side_effect = iter_objects
        storage.delete.side_effect = delete
        return storage

    def test_orphan_sweep_looks_up_each_batch_in_its_own_short_session(self, sessions):
        storage = self._watching_storage([("1", _OLD), ("2", _OLD)], sessions)

        def existing(ids, db):
            assert sessions.open == 1
            return {1}

        assert blob_sweep.sweep_orphaned_blobs(storage, "area", existing, _id_of) == 1
        assert sessions.opened == 1

    def test_unreferenced_sweep_looks_up_each_batch_in_its_own_short_session(self, sessions):
        storage = self._watching_storage([("a", _OLD), ("b", _OLD)], sessions)

        def referenced(keys, db):
            assert sessions.open == 1
            return {"a"}

        assert blob_sweep.sweep_unreferenced_blobs(storage, "area", referenced) == 1
        assert sessions.opened == 1
