"""Tests for known-device persistence."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.models as known_devices_models
from tests._helpers.db import create_sqlite_session

_HASH = "a" * 64
_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _last_seen(db, user_id, device_hash):
    model = known_devices_models.KnownDevice
    return db.execute(
        select(model.last_seen_at).where(model.user_id == user_id, model.device_hash == device_hash)
    ).scalar_one()


def test_a_created_device_is_known_to_its_user_only(db):
    known_devices_crud.create_device(1, _HASH, _NOW, db)

    assert known_devices_crud.has_devices(1, db)
    assert not known_devices_crud.has_devices(2, db)


def test_writes_stage_without_ending_the_transaction(mock_db):
    mock_db.execute.return_value.rowcount = 1

    known_devices_crud.create_device(1, _HASH, _NOW, mock_db)
    known_devices_crud.touch_device(1, _HASH, _NOW, mock_db)
    known_devices_crud.delete_unseen_since(_NOW, 10, mock_db)

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_not_called()


def test_touching_a_known_device_moves_its_last_seen_time(db):
    known_devices_crud.create_device(1, _HASH, _NOW, db)

    assert known_devices_crud.touch_device(1, _HASH, _NOW + timedelta(days=3), db) is True
    assert _last_seen(db, 1, _HASH).replace(tzinfo=UTC) == _NOW + timedelta(days=3)


def test_touching_a_device_of_another_user_changes_nothing(db):
    known_devices_crud.create_device(1, _HASH, _NOW, db)

    assert known_devices_crud.touch_device(2, _HASH, _NOW + timedelta(days=3), db) is False
    assert _last_seen(db, 1, _HASH).replace(tzinfo=UTC) == _NOW


def test_one_device_may_be_known_to_several_users(db):
    known_devices_crud.create_device(1, _HASH, _NOW, db)
    known_devices_crud.create_device(2, _HASH, _NOW, db)

    assert known_devices_crud.has_devices(2, db)


def test_registering_the_same_device_twice_is_a_conflict_that_leaves_the_session_usable(db):
    known_devices_crud.create_device(1, _HASH, _NOW, db)

    with pytest.raises(core_exceptions.ConflictError):
        known_devices_crud.create_device(1, _HASH, _NOW, db)

    assert known_devices_crud.has_devices(1, db)


def test_the_prune_deletes_only_devices_unseen_since_the_cutoff_in_bounded_batches(db):
    cutoff = _NOW - timedelta(days=400)
    for index in range(3):
        known_devices_crud.create_device(1, f"{index}" * 64, cutoff - timedelta(days=1), db)
    known_devices_crud.create_device(1, _HASH, cutoff + timedelta(days=1), db)

    assert known_devices_crud.delete_unseen_since(cutoff, 2, db) == 2
    assert known_devices_crud.delete_unseen_since(cutoff, 2, db) == 1
    assert known_devices_crud.delete_unseen_since(cutoff, 2, db) == 0
    assert known_devices_crud.touch_device(1, _HASH, _NOW, db) is True
