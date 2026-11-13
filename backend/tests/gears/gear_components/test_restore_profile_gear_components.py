import uuid

import modules.gears.gear.crud as gear_crud
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.service as service
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.gears import gear_create

_ARCHIVED_GEAR = uuid.uuid4()


def _record(**overrides):
    return {
        "id": str(uuid.uuid4()),
        "gear_id": str(_ARCHIVED_GEAR),
        "type": "chain",
        "brand": "Shimano",
        "model": "Ultegra",
        **overrides,
    }


def test_a_component_moves_onto_the_restored_gear(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)

    restored = service.restore_profile_gear_components(
        [_record()], MOCK_USER_ID, {"gears": {_ARCHIVED_GEAR: gear.id}}, db
    )

    assert restored == 1
    assert [c.gear_id for c in crud.get_gear_components_user(MOCK_USER_ID, db)] == [gear.id]


def test_a_component_whose_gear_is_not_in_the_archive_is_skipped(db):
    assert service.restore_profile_gear_components([_record()], MOCK_USER_ID, {"gears": {}}, db) == 0
    assert service.restore_profile_gear_components([_record()], MOCK_USER_ID, {}, db) == 0


def test_an_invalid_component_is_skipped(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)

    assert (
        service.restore_profile_gear_components(
            [_record(purchase_value="x")], MOCK_USER_ID, {"gears": {_ARCHIVED_GEAR: gear.id}}, db
        )
        == 0
    )


def test_a_component_retired_before_its_purchase_is_skipped(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)
    record = _record(purchase_date="2026-03-01", retired_date="2026-01-01")

    assert (
        service.restore_profile_gear_components([record], MOCK_USER_ID, {"gears": {_ARCHIVED_GEAR: gear.id}}, db) == 0
    )


def test_no_archived_components_restores_none(db):
    assert service.restore_profile_gear_components([], MOCK_USER_ID, {"gears": {}}, db) == 0


def test_a_price_archived_as_a_number_is_read_as_a_decimal_string(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)

    service.restore_profile_gear_components(
        [_record(purchase_value=45.5)], MOCK_USER_ID, {"gears": {_ARCHIVED_GEAR: gear.id}}, db
    )

    assert crud.get_gear_components_user(MOCK_USER_ID, db)[0].purchase_value == "45.50"


def test_an_archived_expected_kms_is_read_as_expected_usage(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)

    service.restore_profile_gear_components(
        [_record(expected_kms=3000)], MOCK_USER_ID, {"gears": {_ARCHIVED_GEAR: gear.id}}, db
    )

    assert crud.get_gear_components_user(MOCK_USER_ID, db)[0].expected_usage == 3000


def test_an_archived_component_with_its_version_and_stamp_is_restored(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)
    record = _record(user_id=str(uuid.uuid4()), version=2, updated_at="2026-11-11T07:30:00Z")

    assert (
        service.restore_profile_gear_components([record], MOCK_USER_ID, {"gears": {_ARCHIVED_GEAR: gear.id}}, db) == 1
    )
