from datetime import date

import modules.gears.gear.crud as crud
import modules.gears.gear.service as service
from tests._helpers.gears import gear_create


def test_restore_maps_the_archived_id_onto_the_stored_gear(db):
    ids: dict[str, dict[int, int]] = {}

    restored = service.restore_profile_gears([{"id": 5, "nickname": "Garmin", "gear_type": 1}], 1, ids, db)

    assert restored == 1
    assert ids["gears"] == {5: crud.get_gear_user(1, db)[0].id}


def test_a_gear_archived_without_an_id_is_imported_but_names_no_mapping(db):
    ids: dict[str, dict[int, int]] = {}

    restored = service.restore_profile_gears([{"nickname": "Garmin", "gear_type": 1}], 1, ids, db)

    assert restored == 1
    assert ids["gears"] == {}


def test_restore_maps_onto_a_gear_with_the_same_nickname(db):
    existing = crud.create_gear(gear_create("Garmin"), 1, db)
    ids: dict[str, dict[int, int]] = {}

    service.restore_profile_gears([{"id": 5, "nickname": "garmin", "gear_type": 1}], 1, ids, db)

    assert ids["gears"] == {5: existing.id}
    assert len(crud.get_gear_user(1, db)) == 1


def test_restore_drops_provider_ids_that_are_taken(db):
    crud.create_gear(gear_create("Taken", strava_gear_id="b1"), 1, db)
    ids: dict[str, dict[int, int]] = {}

    service.restore_profile_gears([{"id": 5, "nickname": "Garmin", "gear_type": 1, "strava_gear_id": "b1"}], 1, ids, db)

    restored = next(gear for gear in crud.get_gear_user(1, db) if gear.nickname == "Garmin")
    assert ids["gears"] == {5: restored.id}
    assert restored.strava_gear_id is None


def test_an_invalid_gear_is_skipped(db):
    ids: dict[str, dict[int, int]] = {}

    assert service.restore_profile_gears([{"id": 5, "gear_type": 99}], 1, ids, db) == 0


def test_no_archived_gears_still_publishes_an_empty_map(db):
    ids: dict[str, dict[int, int]] = {}

    assert service.restore_profile_gears([], 1, ids, db) == 0
    assert ids == {"gears": {}}


def test_an_archive_from_before_the_rename_maps_the_creation_timestamp_to_its_utc_day(db):
    ids: dict[str, dict[int, int]] = {}
    record = {"id": 5, "nickname": "Old", "gear_type": 1, "created_at": "2024-03-05T23:30:00-02:00"}

    service.restore_profile_gears([record], 1, ids, db)

    assert crud.get_gear_user(1, db)[0].acquired_on == date(2024, 3, 6)


def test_an_archive_with_the_new_field_keeps_it(db):
    ids: dict[str, dict[int, int]] = {}

    service.restore_profile_gears(
        [{"id": 5, "nickname": "New", "gear_type": 1, "acquired_on": "2022-02-03"}], 1, ids, db
    )

    assert crud.get_gear_user(1, db)[0].acquired_on == date(2022, 2, 3)


def test_an_unreadable_creation_timestamp_falls_back_to_the_default(db):
    ids: dict[str, dict[int, int]] = {}

    restored = service.restore_profile_gears(
        [{"id": 5, "nickname": "Odd", "gear_type": 1, "created_at": "nope"}], 1, ids, db
    )

    assert restored == 1
    assert crud.get_gear_user(1, db)[0].acquired_on == date.today()


def test_an_archive_from_before_meters_and_decimal_prices_is_read_as_todays_units(db):
    ids: dict[str, dict[int, int]] = {}
    archived = {"id": 5, "nickname": "Old", "gear_type": 1, "initial_kms": 12.5, "purchase_value": 99.9}

    assert service.restore_profile_gears([archived], 1, ids, db) == 1

    restored = crud.get_gear_user(1, db)[0]
    assert (restored.initial_distance, restored.purchase_value) == (12_500.0, "99.90")


def test_an_archive_with_current_units_is_kept_as_it_is(db):
    ids: dict[str, dict[int, int]] = {}
    archived = {"nickname": "New", "gear_type": 1, "initial_distance": 12_500.0, "purchase_value": "99.90"}

    service.restore_profile_gears([archived], 1, ids, db)

    restored = crud.get_gear_user(1, db)[0]
    assert (restored.initial_distance, restored.purchase_value) == (12_500.0, "99.90")


def test_an_archived_gear_with_its_version_and_stamp_is_restored(db):
    ids: dict[str, dict[int, int]] = {}
    archived = {
        "id": 5,
        "user_id": 3,
        "nickname": "Synced",
        "gear_type": 1,
        "version": 4,
        "updated_at": "2026-11-11T07:30:00Z",
    }

    assert service.restore_profile_gears([archived], 1, ids, db) == 1
    assert crud.get_gear_user(1, db)[0].nickname == "Synced"
