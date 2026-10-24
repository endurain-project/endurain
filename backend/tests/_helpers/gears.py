"""Builders shared by the gears tests."""

import modules.gears.contracts as gears_contracts
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.contributors as gears_contributors
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.schema as gear_components_schema


def gear_create(nickname: str = "Road Bike", **overrides) -> gear_schema.GearCreate:
    """Return a bike create payload with the given overrides."""
    return gear_schema.GearCreate(**{"nickname": nickname, "gear_type": gear_schema.GearType.BIKE, **overrides})


def _component_fields(gear_id: int, overrides: dict) -> dict:
    return {"gear_id": gear_id, "type": "chain", "brand": "Shimano", "model": "XT", **overrides}


def component_create(gear_id: int = 1, **overrides) -> gear_components_schema.GearComponentCreate:
    """Return a chain create payload for a gear with the given overrides."""
    return gear_components_schema.GearComponentCreate(**_component_fields(gear_id, overrides))


def component_update(**fields) -> gear_components_schema.GearComponentUpdate:
    """Return a partial component update carrying only the given fields."""
    return gear_components_schema.GearComponentUpdate(**fields)


def install_readers(
    *,
    usage: gears_contributors.GearUsageReader = lambda gear_id, user_id, db: gears_contracts.UsageTotals(),
    usage_by_window: gears_contributors.GearUsageByWindowReader = lambda gear_id, user_id, windows, db: {},
    components_cost: gears_contributors.ComponentsCostReader = lambda gear_id, user_id, db: 0.0,
    clear_activities_gear: gears_contributors.ActivitiesGearClearer = lambda gear_id, user_id, db: 0,
) -> None:
    """Install gears readers, zero-valued unless overridden."""
    gears_contributor_registry.register(
        gears_contributors.GearReaders(
            usage=usage,
            usage_by_window=usage_by_window,
            components_cost=components_cost,
            clear_activities_gear=clear_activities_gear,
        )
    )
