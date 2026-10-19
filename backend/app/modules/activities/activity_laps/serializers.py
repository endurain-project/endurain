"""ORM↔schema transformation for activity laps.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.activities.activity_laps.models as activity_laps_models
import modules.activities.activity_laps.schema as activity_laps_schema

_LAP_COLUMNS: tuple[str, ...] = (
    "start_time",
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
    "total_cycles",
    "total_calories",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_cadence",
    "max_cadence",
    "avg_power",
    "max_power",
    "total_ascent",
    "total_descent",
    "intensity",
    "lap_trigger",
    "sport",
    "sub_sport",
    "normalized_power",
    "total_work",
    "avg_vertical_oscillation",
    "avg_stance_time",
    "avg_fractional_cadence",
    "max_fractional_cadence",
    "enhanced_avg_pace",
    "enhanced_avg_speed",
    "enhanced_max_pace",
    "enhanced_max_speed",
    "enhanced_min_altitude",
    "enhanced_max_altitude",
    "avg_vertical_ratio",
    "avg_step_length",
)


def to_read_schema(
    orm_lap: activity_laps_models.ActivityLaps,
) -> activity_laps_schema.ActivityLapsRead:
    """Convert an ORM row to its Read schema.

    Args:
        orm_lap: The ORM model instance.

    Returns:
        An ActivityLapsRead schema instance.
    """
    return activity_laps_schema.ActivityLapsRead.model_validate(orm_lap)


def to_orm(lap: dict, activity_id: int) -> activity_laps_models.ActivityLaps:
    """Build an ORM row from a parsed lap dict.

    Args:
        lap: Lap dict from a file parser or profile archive; missing keys become None.
        activity_id: The parent activity ID.

    Returns:
        An unsaved ActivityLaps ORM instance.
    """
    return activity_laps_models.ActivityLaps(
        activity_id=activity_id,
        **{key: lap.get(key) for key in _LAP_COLUMNS},
    )
