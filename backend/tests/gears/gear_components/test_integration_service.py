import modules.gears.gear_components.integration_service as integration
from tests._helpers.gears import component_create


def test_restoring_a_component_stages_it_and_leaves_the_commit_to_the_caller(db, commit_spy):
    created = integration.create_gear_component(component_create(purchase_value=12.0), 1, db)

    commit_spy.assert_not_called()
    assert [c.id for c in integration.get_gear_components_user(1, db)] == [created.id]
    assert integration.get_gear_components_total_cost(1, 1, db) == 12.0
