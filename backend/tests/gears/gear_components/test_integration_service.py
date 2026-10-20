from unittest.mock import MagicMock

import modules.gears.gear_components.integration_service as integration
import modules.gears.gear_components.schema as schema


def test_restoring_a_component_stages_it_and_leaves_the_commit_to_the_caller(db):
    spy = MagicMock(wraps=db.commit)
    db.commit = spy
    component = schema.GearComponentCreate(gear_id=1, type="chain", brand="Shimano", model="XT", purchase_value=12.0)

    created = integration.create_gear_component(component, 1, db)

    spy.assert_not_called()
    assert [c.id for c in integration.get_gear_components_user(1, db)] == [created.id]
    assert integration.get_gear_components_total_cost(1, 1, db) == 12.0
