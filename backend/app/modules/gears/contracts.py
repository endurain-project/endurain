"""Usage figures exchanged between the gears namespace and the module that records activities."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class UsageTotals:
    """Distance and moving time accumulated by a set of activities.

    Attributes:
        distance: Total distance in meters.
        time: Total moving time in seconds.
    """

    distance: float = 0.0
    time: float = 0.0


@dataclass(frozen=True)
class UsageWindow:
    """A date window to accumulate gear usage over.

    Both bounds are **calendar dates**, matched against each activity's date in
    its own timezone rather than against the raw UTC instant — comparing the
    instant put the boundary at UTC midnight, so at UTC-8 an evening ride the day
    before a component was fitted counted towards it, and at UTC+13 a morning ride
    on the fitting day did not count at all.

    Attributes:
        key: Caller-defined identifier echoed back in the results (the gear
            component id, in practice).
        start_date: Inclusive first local day the window covers.
        end_date: Inclusive last local day, or ``None`` while still in use.
    """

    key: int
    start_date: date
    end_date: date | None = None
