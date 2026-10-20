"""Typed callbacks the gears namespace asks composition to install.

Gears sits below the activities module, so it states the questions it needs answered
and ``app/module_registry.py`` installs the answers.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

import modules.gears.contracts as gears_contracts

#: ``(gear_id, user_id, db)`` -> the usage a user recorded against a gear.
GearUsageReader = Callable[[int, int, Session], gears_contracts.UsageTotals]

#: ``(gear_id, user_id, windows, db)`` -> the usage per window key, every key present.
GearUsageByWindowReader = Callable[
    [int, int, Sequence[gears_contracts.UsageWindow], Session], dict[int, gears_contracts.UsageTotals]
]

#: ``(gear_id, user_id, db)`` -> the summed purchase value of a gear's components.
ComponentsCostReader = Callable[[int, int, Session], float]


#: ``(gear_id, user_id, db)`` -> stages unassigning the gear from the user's activities and
#: returns how many it touched.
ActivitiesGearClearer = Callable[[int, int, Session], int]


@dataclass(frozen=True, kw_only=True)
class GearReaders:
    """The answers composition installs for the gears namespace.

    Attributes:
        usage: Totals the usage a user recorded against a gear.
        usage_by_window: Totals a gear's usage per date window.
        components_cost: Sums the purchase value of a gear's components.
        clear_activities_gear: Stages unassigning a gear from the activities that carry it.
    """

    usage: GearUsageReader
    usage_by_window: GearUsageByWindowReader
    components_cost: ComponentsCostReader
    clear_activities_gear: ActivitiesGearClearer
