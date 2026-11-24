"""Storage-side sweeps for blobs no row owns or names, on the platform's storage and the real database."""

import uuid
from time import time

import jasil.runtime as platform_runtime
import pytest
from jasil.providers import StorageBackendUnavailableError
from sqlalchemy import select

import core.blob_sweep as blob_sweep
import core.database as core_database
import modules.users.users.models as users_models
from tests._factories.users import make_user

_AREA = "sweep_area"
_HOUR = 3600


@pytest.fixture
def storage():
    return platform_runtime.get_active_platform().storage


@pytest.fixture
def clock(monkeypatch):
    """Return a function that sets how far ahead of the files' modification time the sweeps think it is."""
    started = time()

    def ahead(seconds: float) -> None:
        monkeypatch.setattr(blob_sweep, "time", lambda: started + seconds)

    return ahead


def _keys(storage) -> set[str]:
    return {key for key, _modified in storage.iter_objects(_AREA, "")}


def _id_of(key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(key)
    except ValueError:
        return None


def _users_that_exist(ids: list[uuid.UUID], db) -> set[uuid.UUID]:
    return set(db.scalars(select(users_models.Users.id).where(users_models.Users.id.in_(ids))))


@pytest.fixture
def user_id(committed_sessions) -> uuid.UUID:
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created.id


class TestSweepOrphanedBlobs:
    def test_deletes_only_blobs_whose_owner_is_gone(self, storage, user_id, clock):
        gone = uuid.uuid4()
        storage.save(_AREA, str(user_id), b"kept")
        storage.save(_AREA, str(gone), b"orphan")
        clock(2 * _HOUR)

        removed = blob_sweep.sweep_orphaned_blobs(storage, _AREA, _users_that_exist, _id_of)

        assert removed == 1
        assert _keys(storage) == {str(user_id)}

    def test_skips_blobs_younger_than_the_age_guard(self, storage, clock):
        gone = uuid.uuid4()
        storage.save(_AREA, str(gone), b"fresh")
        clock(_HOUR // 2)

        removed = blob_sweep.sweep_orphaned_blobs(storage, _AREA, _users_that_exist, _id_of)

        assert removed == 0
        assert _keys(storage) == {str(gone)}

    def test_leaves_keys_it_does_not_own(self, storage, clock):
        storage.save(_AREA, "not-an-id", b"foreign")
        clock(2 * _HOUR)

        removed = blob_sweep.sweep_orphaned_blobs(storage, _AREA, _users_that_exist, _id_of)

        assert removed == 0
        assert _keys(storage) == {"not-an-id"}

    def test_an_empty_area_does_not_query_existence(self, storage, clock):
        looked_up: list[list[uuid.UUID]] = []

        def lookup(ids, db):
            looked_up.append(ids)
            return set()

        assert blob_sweep.sweep_orphaned_blobs(storage, _AREA, lookup, _id_of) == 0
        assert looked_up == []


class TestSweepUnreferencedBlobs:
    def test_deletes_only_old_blobs_no_row_names(self, storage, clock):
        for key in ("1_a.jpg", "1_b.jpg"):
            storage.save(_AREA, key, b"x")
        clock(2 * _HOUR)
        storage.save(_AREA, "1_c.jpg", b"x")

        removed = blob_sweep.sweep_unreferenced_blobs(storage, _AREA, lambda keys, db: {"1_a.jpg"})

        assert removed == 2
        assert _keys(storage) == {"1_a.jpg"}


class TestNoSessionAcrossStorageCalls:
    """A storage call on object storage is a network round trip, so no connection may wait on it."""

    @pytest.fixture
    def watched(self, storage, committed_sessions):
        """Storage that fails the test when a database connection is checked out during a call."""

        class Watching:
            def iter_objects(self, area, prefix=""):
                for item in storage.iter_objects(area, prefix):
                    assert core_database.engine.pool.checkedout() == 0, "a session was open while listing"
                    yield item

            def delete(self, area, key):
                assert core_database.engine.pool.checkedout() == 0, "a session was open while deleting"
                storage.delete(area, key)

        return Watching()

    def test_orphan_sweep_looks_up_each_batch_in_its_own_short_session(self, watched, storage, user_id, clock):
        storage.save(_AREA, str(user_id), b"kept")
        storage.save(_AREA, str(uuid.uuid4()), b"orphan")
        clock(2 * _HOUR)
        lookups = []

        def existing(ids, db):
            db.execute(select(1))
            assert core_database.engine.pool.checkedout() == 1
            lookups.append(ids)
            return _users_that_exist(ids, db)

        assert blob_sweep.sweep_orphaned_blobs(watched, _AREA, existing, _id_of) == 1
        assert len(lookups) == 1

    def test_unreferenced_sweep_looks_up_each_batch_in_its_own_short_session(self, watched, storage, clock):
        for key in ("a", "b"):
            storage.save(_AREA, key, b"x")
        clock(2 * _HOUR)
        lookups = []

        def referenced(keys, db):
            db.execute(select(1))
            assert core_database.engine.pool.checkedout() == 1
            lookups.append(keys)
            return {"a"}

        assert blob_sweep.sweep_unreferenced_blobs(watched, _AREA, referenced) == 1
        assert len(lookups) == 1


class TestSweepAgedBlobs:
    def test_removes_blobs_older_than_the_age(self, storage, clock):
        storage.save(_AREA, "old", b"x")
        clock(7200)

        assert blob_sweep.sweep_aged_blobs(storage, _AREA, 3600) == 1
        assert _keys(storage) == set()

    def test_a_blob_younger_than_the_age_stays(self, storage, clock):
        storage.save(_AREA, "new", b"x")
        clock(60)

        assert blob_sweep.sweep_aged_blobs(storage, _AREA, 3600) == 0
        assert _keys(storage) == {"new"}

    def test_a_failing_delete_does_not_stop_the_sweep(self, storage, clock):
        for key in ("a", "b"):
            storage.save(_AREA, key, b"x")
        clock(7200)

        class Flaky:
            def iter_objects(self, area, prefix=""):
                return storage.iter_objects(area, prefix)

            def delete(self, area, key):
                if key == "a":
                    raise StorageBackendUnavailableError("busy")
                storage.delete(area, key)

        assert blob_sweep.sweep_aged_blobs(Flaky(), _AREA, 3600) == 1
        assert _keys(storage) == {"a"}
