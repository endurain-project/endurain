from datetime import date
from unittest.mock import MagicMock

import pytest

import module_registry
import modules.gears.contracts as gears_contracts
import modules.gears.contributor_registry as registry


def test_nothing_is_answered_until_composition_installs_the_readers():
    with pytest.raises(RuntimeError, match="gear usage"):
        registry.gear_usage(1, 1, MagicMock())
    with pytest.raises(RuntimeError, match="gear usage by window"):
        registry.gear_usage_by_window(1, 1, [], MagicMock())
    with pytest.raises(RuntimeError, match="components cost"):
        registry.components_total_cost(1, 1, MagicMock())


def test_installed_readers_are_called_with_the_callers_arguments():
    db = MagicMock()
    window = gears_contracts.UsageWindow(key=3, start_date=date(2024, 1, 1))
    usage = MagicMock(return_value=gears_contracts.UsageTotals(distance=1.0, time=2.0))
    by_window = MagicMock(return_value={3: gears_contracts.UsageTotals()})
    cost = MagicMock(return_value=5.0)
    registry.register_gear_usage_reader(usage)
    registry.register_gear_usage_by_window_reader(by_window)
    registry.register_components_cost_reader(cost)

    assert registry.gear_usage(1, 2, db).distance == 1.0
    assert registry.gear_usage_by_window(1, 2, [window], db) == {3: gears_contracts.UsageTotals()}
    assert registry.components_total_cost(1, 2, db) == 5.0
    usage.assert_called_once_with(1, 2, db)
    by_window.assert_called_once_with(1, 2, [window], db)
    cost.assert_called_once_with(1, 2, db)


def test_clear_removes_every_reader():
    registry.register_components_cost_reader(lambda gear_id, user_id, db: 1.0)

    registry.clear()

    with pytest.raises(RuntimeError):
        registry.components_total_cost(1, 1, MagicMock())


def test_composition_installs_all_three_readers_idempotently():
    module_registry.configure_gear_contributors()
    module_registry.configure_gear_contributors()

    for name in ("_gear_usage_reader", "_gear_usage_by_window_reader", "_components_cost_reader"):
        assert getattr(registry, name) is not None
