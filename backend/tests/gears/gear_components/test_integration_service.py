"""The gear component integration surface other modules call, on the real database."""

import uuid

import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.integration_service as integration
from tests._factories.gears import component_payload, make_gear
from tests._factories.users import make_user


def test_restoring_a_component_stages_it_and_leaves_the_commit_to_the_caller(committed_sessions):
    with committed_sessions() as db:
        owner = make_user(db)
        gear = make_gear(db, owner.id)
        db.commit()
    archived_gear = uuid.uuid4()
    archived = {
        "gear_id": str(archived_gear),
        "type": "chain",
        "brand": "Shimano",
        "model": "XT",
        "purchase_value": "12.00",
    }

    with committed_sessions() as db:
        restored = integration.restore_profile_gear_components(
            [archived], owner.id, {"gears": {archived_gear: gear.id}}, db
        )
        assert restored == 1
        assert len(integration.get_gear_components_user(owner.id, db)) == 1
        assert integration.get_gear_components_total_cost(gear.id, owner.id, db) == 12.0
        db.rollback()

    with committed_sessions() as db:
        assert integration.get_gear_components_user(owner.id, db) == []


def test_components_outside_a_gear_type_are_counted_by_the_catalogue_of_that_type(db, user):
    gear = make_gear(db, user.id)
    crud.create_gear_component(component_payload(gear.id, type="chain"), user.id, db)
    crud.create_gear_component(component_payload(gear.id, type="saddle"), user.id, db)

    count = integration.count_components_outside_gear_type
    assert count(gear.id, user.id, gear_schema.GearType.BIKE, db) == 0
    assert count(gear.id, user.id, gear_schema.GearType.SHOES, db) == 2
    # A type without a catalogue accepts any component.
    assert count(gear.id, user.id, gear_schema.GearType.WETSUIT, db) == 0
