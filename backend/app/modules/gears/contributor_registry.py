"""Process-local store of the readers that composition installs for the gears namespace."""

from collections.abc import Sequence

from sqlalchemy.orm import Session

import modules.gears.contracts as gears_contracts
import modules.gears.contributors as gears_contributors

_gear_usage_reader: gears_contributors.GearUsageReader | None = None
_gear_usage_by_window_reader: gears_contributors.GearUsageByWindowReader | None = None
_components_cost_reader: gears_contributors.ComponentsCostReader | None = None

_NOT_INSTALLED = "The gears contributor '{name}' is not installed; call module_registry.configure_gear_contributors()"


def register_gear_usage_reader(reader: gears_contributors.GearUsageReader) -> None:
    """Install the reader that totals the usage recorded against a gear.

    Args:
        reader: Callable answering ``(gear_id, user_id, db)``.
    """
    global _gear_usage_reader
    _gear_usage_reader = reader


def register_gear_usage_by_window_reader(reader: gears_contributors.GearUsageByWindowReader) -> None:
    """Install the reader that totals a gear's usage per date window.

    Args:
        reader: Callable answering ``(gear_id, user_id, windows, db)``.
    """
    global _gear_usage_by_window_reader
    _gear_usage_by_window_reader = reader


def register_components_cost_reader(reader: gears_contributors.ComponentsCostReader) -> None:
    """Install the reader that sums the purchase value of a gear's components.

    Args:
        reader: Callable answering ``(gear_id, user_id, db)``.
    """
    global _components_cost_reader
    _components_cost_reader = reader


def gear_usage(gear_id: int, user_id: int, db: Session) -> gears_contracts.UsageTotals:
    """Return the distance and moving time a user recorded against a gear.

    Args:
        gear_id: The gear to total.
        user_id: The gear's owner; only their activities count.
        db: Database session.

    Returns:
        The gear's totals, zero when it has no activities.

    Raises:
        RuntimeError: If composition has not installed the reader.
    """
    if _gear_usage_reader is None:
        raise RuntimeError(_NOT_INSTALLED.format(name="gear usage"))
    return _gear_usage_reader(gear_id, user_id, db)


def gear_usage_by_window(
    gear_id: int,
    user_id: int,
    windows: Sequence[gears_contracts.UsageWindow],
    db: Session,
) -> dict[int, gears_contracts.UsageTotals]:
    """Return a gear's usage per date window.

    Args:
        gear_id: The gear to total.
        user_id: The gear's owner; only their activities count.
        windows: The windows to total over, keyed by the caller.
        db: Database session.

    Returns:
        Totals per window key, every requested key present.

    Raises:
        RuntimeError: If composition has not installed the reader.
    """
    if _gear_usage_by_window_reader is None:
        raise RuntimeError(_NOT_INSTALLED.format(name="gear usage by window"))
    return _gear_usage_by_window_reader(gear_id, user_id, windows, db)


def components_total_cost(gear_id: int, user_id: int, db: Session) -> float:
    """Return the summed purchase value of a gear's components.

    Args:
        gear_id: The gear whose components to sum.
        user_id: The gear's owner.
        db: Database session.

    Returns:
        The total cost, zero when the gear has no priced components.

    Raises:
        RuntimeError: If composition has not installed the reader.
    """
    if _components_cost_reader is None:
        raise RuntimeError(_NOT_INSTALLED.format(name="components cost"))
    return _components_cost_reader(gear_id, user_id, db)


def clear() -> None:
    """Remove every installed reader."""
    global _gear_usage_reader, _gear_usage_by_window_reader, _components_cost_reader
    _gear_usage_reader = None
    _gear_usage_by_window_reader = None
    _components_cost_reader = None
