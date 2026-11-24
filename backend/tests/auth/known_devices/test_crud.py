"""Known-device persistence on PostgreSQL: one row per user and device, generations and the prune."""

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.models as known_devices_models
from tests._factories.users import make_user

_HASH = "a" * 64
_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
_DESCRIPTION = known_devices_contracts.DeviceDescription(browser="Firefox", operating_system="Linux", device_type="PC")
_SAFARI = known_devices_contracts.DeviceDescription(browser="Safari", operating_system="Mac OS X", device_type="PC")


def _row(db, user_id, device_hash) -> known_devices_models.KnownDevice:
    model = known_devices_models.KnownDevice
    return db.scalars(sa.select(model).where(model.user_id == user_id, model.device_hash == device_hash)).one()


class TestCreate:
    def test_a_created_device_is_known_to_its_user_only(self, db):
        user, other = make_user(db), make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)

        assert known_devices_crud.has_devices(user.id, db)
        assert not known_devices_crud.has_devices(other.id, db)

    def test_one_device_may_be_known_to_several_users(self, db):
        user, other = make_user(db), make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)
        known_devices_crud.create_device(other.id, _HASH, 0, _NOW, _DESCRIPTION, db)

        assert known_devices_crud.has_device(other.id, _HASH, 0, db)

    def test_registering_the_same_device_twice_is_a_conflict_that_leaves_the_session_usable(self, db):
        user = make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)

        with pytest.raises(core_exceptions.ConflictError):
            known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)

        assert known_devices_crud.count_devices(user.id, 0, db) == 1

    def test_deleting_a_user_deletes_their_devices(self, db):
        user = make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert not known_devices_crud.has_devices(user.id, db)


class TestGenerations:
    def test_a_device_is_known_only_under_the_generation_it_was_registered_in(self, db):
        user = make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)

        assert known_devices_crud.has_device(user.id, _HASH, 0, db)
        assert not known_devices_crud.has_device(user.id, _HASH, 1, db)
        assert known_devices_crud.has_devices(user.id, db)

    def test_touching_a_device_moves_its_last_seen_time_and_description_within_its_generation(self, db):
        user, other = make_user(db), make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)
        later = _NOW + timedelta(days=3)

        assert known_devices_crud.touch_device(other.id, _HASH, 0, later, _SAFARI, db) is False
        assert known_devices_crud.touch_device(user.id, _HASH, 1, later, _SAFARI, db) is False
        assert known_devices_crud.touch_device(user.id, _HASH, 0, later, _SAFARI, db) is True

        db.expire_all()
        row = _row(db, user.id, _HASH)
        assert row.last_seen_at == later
        assert (row.browser, row.operating_system) == ("Safari", "Mac OS X")
        assert row.created_at == _NOW

    def test_restamping_registers_a_device_of_an_older_generation_again(self, db):
        user = make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 0, _NOW, _DESCRIPTION, db)
        later = _NOW + timedelta(days=3)

        assert known_devices_crud.restamp_device(user.id, _HASH, 0, later, _SAFARI, db) is False
        assert known_devices_crud.restamp_device(user.id, _HASH, 1, later, _SAFARI, db) is True

        db.expire_all()
        row = _row(db, user.id, _HASH)
        assert (row.security_generation, row.created_at, row.last_seen_at) == (1, later, later)
        assert row.browser == "Safari"


class TestListAndForget:
    def test_a_page_holds_the_current_generation_latest_sign_in_first_and_the_count_covers_every_page(self, db):
        user, other = make_user(db), make_user(db)
        for index, hours in enumerate((1, 3, 2)):
            known_devices_crud.create_device(
                user.id, str(index) * 64, 1, _NOW + timedelta(hours=hours), _DESCRIPTION, db
            )
        known_devices_crud.create_device(user.id, "e" * 64, 0, _NOW + timedelta(hours=9), _DESCRIPTION, db)
        known_devices_crud.create_device(other.id, "f" * 64, 1, _NOW, _DESCRIPTION, db)

        first = known_devices_crud.get_devices_page(user.id, 1, 2, 0, db)
        rest = known_devices_crud.get_devices_page(user.id, 1, 2, 2, db)

        assert [row.device_hash for row in first] == ["1" * 64, "2" * 64]
        assert [row.device_hash for row in rest] == ["0" * 64]
        assert known_devices_crud.count_devices(user.id, 1, db) == 3

    def test_a_device_is_found_and_deleted_only_by_its_owner_under_the_current_generation(self, db):
        user, other = make_user(db), make_user(db)
        known_devices_crud.create_device(user.id, _HASH, 1, _NOW, _DESCRIPTION, db)
        device_id = _row(db, user.id, _HASH).id

        assert known_devices_crud.get_device_hash(device_id, user.id, 1, db) == _HASH
        assert known_devices_crud.get_device_hash(device_id, other.id, 1, db) is None
        assert known_devices_crud.get_device_hash(device_id, user.id, 0, db) is None
        assert known_devices_crud.delete_device(device_id, other.id, 1, db) is None
        assert known_devices_crud.delete_device(device_id, user.id, 0, db) is None
        assert known_devices_crud.delete_device(device_id, user.id, 1, db) == _HASH
        assert not known_devices_crud.has_devices(user.id, db)

    def test_deleting_the_others_keeps_one_device_of_any_generation_and_returns_the_deleted_hashes(self, db):
        user, other = make_user(db), make_user(db)
        known_devices_crud.create_device(user.id, "1" * 64, 0, _NOW, _DESCRIPTION, db)
        known_devices_crud.create_device(user.id, "2" * 64, 1, _NOW, _DESCRIPTION, db)
        known_devices_crud.create_device(user.id, "3" * 64, 1, _NOW, _DESCRIPTION, db)
        known_devices_crud.create_device(other.id, "4" * 64, 1, _NOW, _DESCRIPTION, db)

        deleted = known_devices_crud.delete_devices_except(user.id, "2" * 64, db)

        assert sorted(deleted) == ["1" * 64, "3" * 64]
        assert known_devices_crud.has_device(user.id, "2" * 64, 1, db)
        assert known_devices_crud.has_device(other.id, "4" * 64, 1, db)

    def test_deleting_the_others_without_a_device_to_keep_deletes_them_all(self, db):
        user = make_user(db)
        known_devices_crud.create_device(user.id, "1" * 64, 0, _NOW, _DESCRIPTION, db)
        known_devices_crud.create_device(user.id, "2" * 64, 1, _NOW, _DESCRIPTION, db)

        assert sorted(known_devices_crud.delete_devices_except(user.id, None, db)) == ["1" * 64, "2" * 64]
        assert not known_devices_crud.has_devices(user.id, db)


class TestPrune:
    def test_only_devices_unseen_since_the_cutoff_are_deleted_in_bounded_batches(self, db):
        user = make_user(db)
        cutoff = _NOW - timedelta(days=400)
        for index in range(3):
            known_devices_crud.create_device(user.id, f"{index}" * 64, 0, cutoff - timedelta(days=1), _DESCRIPTION, db)
        known_devices_crud.create_device(user.id, _HASH, 0, cutoff + timedelta(days=1), _DESCRIPTION, db)

        assert known_devices_crud.delete_unseen_since(cutoff, 2, db) == 2
        assert known_devices_crud.delete_unseen_since(cutoff, 2, db) == 1
        assert known_devices_crud.delete_unseen_since(cutoff, 2, db) == 0
        assert known_devices_crud.has_device(user.id, _HASH, 0, db)
