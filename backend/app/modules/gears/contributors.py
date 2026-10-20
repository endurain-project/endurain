"""Typed callbacks the gears namespace asks composition to install.

Gears sits below the activities module, so it states the questions it needs answered
and ``app/module_registry.py`` installs the answers.
"""

from collections.abc import Callable, Sequence

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
