import pytest

import module_registry
import modules.activities.activity.integration_service as activity_integration
import modules.gears.contributor_registry as registry
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.users.users_default_gear.integration_service as users_default_gear_integration


@pytest.fixture(autouse=True)
def _clean_gears_registry():
    registry.clear()
    yield
    registry.clear()


def test_nothing_is_answered_until_composition_installs_the_readers():
    with pytest.raises(RuntimeError, match="configure_gear_contributors"):
        registry.readers()


def test_composition_installs_the_readers_and_clear_removes_them():
    module_registry.configure_gear_contributors()
    assert registry.readers() is not None

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
    assert readers.clear_default_gear is users_default_gear_integration.clear_default_gears
    assert readers.record_component_deletions is gear_components_integration.record_gear_component_deletions
