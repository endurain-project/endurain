"""Typed callbacks the gears namespace asks composition to install.

Gears sits below the activities module, so it states the questions it needs answered
and ``app/module_registry.py`` installs the answers.
"""

import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

import modules.gears.contracts as gears_contracts
import modules.gears.gear.schema as gears_schema

#: ``(gear_id, user_id, db)`` -> the usage a user recorded against a gear.
GearUsageReader = Callable[[uuid.UUID, uuid.UUID, Session], gears_contracts.UsageTotals]

#: ``(gear_id, user_id, windows, db)`` -> the usage per window key, every key present.
GearUsageByWindowReader = Callable[
    [uuid.UUID, uuid.UUID, Sequence[gears_contracts.UsageWindow], Session], dict[uuid.UUID, gears_contracts.UsageTotals]
]

#: ``(gear_id, user_id, db)`` -> the summed purchase value of a gear's components.
ComponentsCostReader = Callable[[uuid.UUID, uuid.UUID, Session], float]

#: ``(gear_id, user_id, gear_type, db)`` -> how many of a gear's components are not valid for a gear type.
ComponentsOutsideTypeCounter = Callable[[uuid.UUID, uuid.UUID, gears_schema.GearType, Session], int]

#: ``(gear_id, user_id, db)`` -> stages unassigning the gear from the user's activities and
#: returns how many it touched.
ActivitiesGearClearer = Callable[[uuid.UUID, uuid.UUID, Session], int]

#: ``(gear_ids, user_id, db)`` -> stages unassigning the gears from the user's default gear settings.
DefaultGearClearer = Callable[[Collection[uuid.UUID], uuid.UUID, Session], None]

#: ``(gear_ids, user_id, db)`` -> stages a deletion record for every component of the gears, which deleting the
#: gears cascades away.
ComponentDeletionsRecorder = Callable[[Collection[uuid.UUID], uuid.UUID, Session], None]


@dataclass(frozen=True, kw_only=True)
class GearReaders:
    """The answers composition installs for the gears namespace.

    Attributes:
        usage: Totals the usage a user recorded against a gear.
        usage_by_window: Totals a gear's usage per date window.
        components_cost: Sums the purchase value of a gear's components.
        count_components_outside_type: Counts a gear's components whose type is not valid for a gear type.
        clear_activities_gear: Stages unassigning a gear from the activities that carry it.
        clear_default_gear: Stages unassigning gears from the user's default gear settings.
        record_component_deletions: Stages a deletion record for every component of gears about to be deleted.
    """

    usage: GearUsageReader
    usage_by_window: GearUsageByWindowReader
    components_cost: ComponentsCostReader
    count_components_outside_type: ComponentsOutsideTypeCounter
    clear_activities_gear: ActivitiesGearClearer
    clear_default_gear: DefaultGearClearer
    record_component_deletions: ComponentDeletionsRecorder
