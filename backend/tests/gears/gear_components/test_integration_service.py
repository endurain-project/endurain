import uuid

import modules.gears.gear.crud as gear_crud
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as crud
import modules.gears.gear_components.integration_service as integration
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.gears import component_create, gear_create


def test_restoring_a_component_stages_it_and_leaves_the_commit_to_the_caller(db, commit_spy):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)
    archived_gear = uuid.uuid4()

    restored = integration.restore_profile_gear_components(
        [
            {
                "gear_id": str(archived_gear),
                "type": "chain",
                "brand": "Shimano",
                "model": "XT",
                "purchase_value": "12.00",
            }
        ],
        MOCK_USER_ID,
        {"gears": {archived_gear: gear.id}},
        db,
    )

    commit_spy.assert_not_called()
    assert restored == 1
    assert len(integration.get_gear_components_user(MOCK_USER_ID, db)) == 1
    assert integration.get_gear_components_total_cost(gear.id, MOCK_USER_ID, db) == 12.0


def test_components_outside_a_gear_type_are_counted_by_the_catalogue_of_that_type(db):
    gear = gear_crud.create_gear(gear_create(), MOCK_USER_ID, db)
    crud.create_gear_component(component_create(gear.id, type="chain"), MOCK_USER_ID, db)
    crud.create_gear_component(component_create(gear.id, type="saddle"), MOCK_USER_ID, db)

    count = integration.count_components_outside_gear_type
    assert count(gear.id, MOCK_USER_ID, gear_schema.GearType.BIKE, db) == 0
    assert count(gear.id, MOCK_USER_ID, gear_schema.GearType.SHOES, db) == 2
    # A type without a catalogue accepts any component.
    assert count(gear.id, MOCK_USER_ID, gear_schema.GearType.WETSUIT, db) == 0
