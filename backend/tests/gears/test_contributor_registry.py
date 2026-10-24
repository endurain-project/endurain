from unittest.mock import MagicMock

import pytest

import module_registry
import modules.activities.activity.integration_service as activity_integration
import modules.gears.contributor_registry as registry
import modules.gears.gear_components.integration_service as gear_components_integration
from tests._helpers.gears import install_readers


def test_nothing_is_answered_until_composition_installs_the_readers():
    with pytest.raises(RuntimeError, match="configure_gear_contributors"):
        registry.readers()


def test_register_replaces_and_clear_removes_the_readers():
    cost = MagicMock(return_value=5.0)
    install_readers()
    install_readers(components_cost=cost)

    assert registry.readers().components_cost(1, 2, "db") == 5.0
    cost.assert_called_once_with(1, 2, "db")

    registry.clear()
    with pytest.raises(RuntimeError):
        registry.readers()


def test_composition_installs_the_activities_and_component_readers():
    module_registry.configure_gear_contributors()

    readers = registry.readers()
    assert readers.usage is activity_integration.get_gear_usage_totals
    assert readers.usage_by_window is activity_integration.get_gear_usage_totals_by_window
    assert readers.components_cost is gear_components_integration.get_gear_components_total_cost
    assert readers.clear_activities_gear is activity_integration.clear_activities_gear
