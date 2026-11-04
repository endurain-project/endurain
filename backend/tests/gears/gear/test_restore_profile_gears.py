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
