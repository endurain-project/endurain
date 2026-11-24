import uuid

import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.service as service
from tests._factories.gears import make_gear

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


def test_a_component_moves_onto_the_restored_gear(db, user):
    gear = make_gear(db, user.id)

    restored = service.restore_profile_gear_components([_record()], user.id, {"gears": {_ARCHIVED_GEAR: gear.id}}, db)

    assert restored == 1
    assert [c.gear_id for c in crud.get_gear_components_user(user.id, db)] == [gear.id]


def test_a_component_whose_gear_is_not_in_the_archive_is_skipped(db, user):
    assert service.restore_profile_gear_components([_record()], user.id, {"gears": {}}, db) == 0
    assert service.restore_profile_gear_components([_record()], user.id, {}, db) == 0


def test_an_invalid_component_is_skipped(db, user):
    gear = make_gear(db, user.id)

    assert (
        service.restore_profile_gear_components(
            [_record(purchase_value="x")], user.id, {"gears": {_ARCHIVED_GEAR: gear.id}}, db
        )
        == 0
    )


def test_a_component_retired_before_its_purchase_is_skipped(db, user):
    gear = make_gear(db, user.id)
    record = _record(purchase_date="2026-03-01", retired_date="2026-01-01")

    assert service.restore_profile_gear_components([record], user.id, {"gears": {_ARCHIVED_GEAR: gear.id}}, db) == 0


def test_no_archived_components_restores_none(db, user):
    assert service.restore_profile_gear_components([], user.id, {"gears": {}}, db) == 0


def test_an_archived_component_with_its_version_and_stamp_is_restored(db, user):
    gear = make_gear(db, user.id)
    record = _record(user_id=str(uuid.uuid4()), version=2, updated_at="2026-11-11T07:30:00Z")

    assert service.restore_profile_gear_components([record], user.id, {"gears": {_ARCHIVED_GEAR: gear.id}}, db) == 1
