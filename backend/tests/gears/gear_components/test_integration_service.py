import modules.gears.gear.crud as gear_crud
import modules.gears.gear_components.integration_service as integration
from tests._helpers.gears import gear_create


def test_restoring_a_component_stages_it_and_leaves_the_commit_to_the_caller(db, commit_spy):
    gear = gear_crud.create_gear(gear_create(), 1, db)

    restored = integration.restore_profile_gear_components(
        [{"gear_id": 5, "type": "chain", "brand": "Shimano", "model": "XT", "purchase_value": 12.0}],
        1,
        {"gears": {5: gear.id}},
        db,
    )

    commit_spy.assert_not_called()
    assert restored == 1
    assert len(integration.get_gear_components_user(1, db)) == 1
    assert integration.get_gear_components_total_cost(gear.id, 1, db) == 12.0
