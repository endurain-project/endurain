import uuid
from datetime import date

import pytest

import modules.gears.gear.crud as crud
import modules.gears.gear.service as service
import modules.users.users_profile.contracts as users_profile_contracts
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.gears import gear_create

_ARCHIVED_UUID = uuid.uuid4()
_ARCHIVED_ID = str(_ARCHIVED_UUID)


@pytest.mark.parametrize("archived_id", [7, "7", "not-a-uuid"])
def test_a_gear_archived_with_a_non_uuid_id_is_imported_but_names_no_mapping(db, archived_id):
    ids: users_profile_contracts.ProfileIdMaps = {}

    service.restore_profile_gears([{"id": archived_id, "nickname": "Garmin", "gear_type": 1}], MOCK_USER_ID, ids, db)

    assert ids["gears"] == {}
    assert len(crud.get_gear_user(MOCK_USER_ID, db)) == 1


def test_restore_maps_the_archived_id_onto_the_stored_gear(db):
    ids: users_profile_contracts.ProfileIdMaps = {}

    restored = service.restore_profile_gears(
        [{"id": _ARCHIVED_ID, "nickname": "Garmin", "gear_type": 1}], MOCK_USER_ID, ids, db
    )

    assert restored == 1
    assert ids["gears"] == {_ARCHIVED_UUID: crud.get_gear_user(MOCK_USER_ID, db)[0].id}


def test_a_gear_archived_without_an_id_is_imported_but_names_no_mapping(db):
    ids: users_profile_contracts.ProfileIdMaps = {}

    restored = service.restore_profile_gears([{"nickname": "Garmin", "gear_type": 1}], MOCK_USER_ID, ids, db)

    assert restored == 1
    assert ids["gears"] == {}


def test_restore_maps_onto_a_gear_with_the_same_nickname(db):
    existing = crud.create_gear(gear_create("Garmin"), MOCK_USER_ID, db)
    ids: users_profile_contracts.ProfileIdMaps = {}

    service.restore_profile_gears([{"id": _ARCHIVED_ID, "nickname": "garmin", "gear_type": 1}], MOCK_USER_ID, ids, db)

    assert ids["gears"] == {_ARCHIVED_UUID: existing.id}
    assert len(crud.get_gear_user(MOCK_USER_ID, db)) == 1


def test_restore_drops_provider_ids_that_are_taken(db):
    crud.create_gear(gear_create("Taken", strava_gear_id="b1"), MOCK_USER_ID, db)
    ids: users_profile_contracts.ProfileIdMaps = {}

    service.restore_profile_gears(
        [{"id": _ARCHIVED_ID, "nickname": "Garmin", "gear_type": 1, "strava_gear_id": "b1"}], MOCK_USER_ID, ids, db
    )

    restored = next(gear for gear in crud.get_gear_user(MOCK_USER_ID, db) if gear.nickname == "Garmin")
    assert ids["gears"] == {_ARCHIVED_UUID: restored.id}
    assert restored.strava_gear_id is None


def test_an_invalid_gear_is_skipped(db):
    ids: users_profile_contracts.ProfileIdMaps = {}

    assert service.restore_profile_gears([{"id": _ARCHIVED_ID, "gear_type": 99}], MOCK_USER_ID, ids, db) == 0


def test_no_archived_gears_still_publishes_an_empty_map(db):
    ids: users_profile_contracts.ProfileIdMaps = {}

    assert service.restore_profile_gears([], MOCK_USER_ID, ids, db) == 0
    assert ids == {"gears": {}}


def test_an_archive_with_the_new_field_keeps_it(db):
    ids: users_profile_contracts.ProfileIdMaps = {}

    service.restore_profile_gears(
        [{"id": _ARCHIVED_ID, "nickname": "New", "gear_type": 1, "acquired_on": "2022-02-03"}], MOCK_USER_ID, ids, db
    )

    assert crud.get_gear_user(MOCK_USER_ID, db)[0].acquired_on == date(2022, 2, 3)


def test_an_archive_with_current_units_is_kept_as_it_is(db):
    ids: users_profile_contracts.ProfileIdMaps = {}
    archived = {"nickname": "New", "gear_type": 1, "initial_distance": 12_500.0, "purchase_value": "99.90"}

    service.restore_profile_gears([archived], MOCK_USER_ID, ids, db)

    restored = crud.get_gear_user(MOCK_USER_ID, db)[0]
    assert (restored.initial_distance, restored.purchase_value) == (12_500.0, "99.90")


def test_an_archived_gear_with_its_version_and_stamp_is_restored(db):
    ids: users_profile_contracts.ProfileIdMaps = {}
    archived = {
        "id": _ARCHIVED_ID,
        "user_id": str(uuid.uuid4()),
        "nickname": "Synced",
        "gear_type": 1,
        "version": 4,
        "updated_at": "2026-11-11T07:30:00Z",
    }

    assert service.restore_profile_gears([archived], MOCK_USER_ID, ids, db) == 1
    assert crud.get_gear_user(MOCK_USER_ID, db)[0].nickname == "Synced"
