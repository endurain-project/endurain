"""Activity laps schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

import core.pagination as core_pagination

_FLOAT_FIELDS: tuple[str, ...] = (
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
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


class ActivityLapsBase(BaseModel):
    """
    Base schema for activity laps.

    Attributes:
        start_time: Lap start time ISO string.
        start_position_lat: Start latitude.
        start_position_long: Start longitude.
        end_position_lat: End latitude.
        end_position_long: End longitude.
        total_elapsed_time: Total elapsed time.
        total_timer_time: Total timer time.
        total_distance: Total distance.
        total_cycles: Total cycles.
        total_calories: Total calories.
        avg_heart_rate: Average heart rate.
        max_heart_rate: Maximum heart rate.
        avg_cadence: Average cadence.
        max_cadence: Maximum cadence.
        avg_power: Average power.
        max_power: Maximum power.
        total_ascent: Total ascent.
        total_descent: Total descent.
        intensity: Lap intensity.
        lap_trigger: Lap trigger type.
        sport: Sport type.
        sub_sport: Sub sport type.
        normalized_power: Normalized power.
        total_work: Total work.
        avg_vertical_oscillation: Avg oscillation.
        avg_stance_time: Average stance time.
        avg_fractional_cadence: Avg frac cadence.
        max_fractional_cadence: Max frac cadence.
        enhanced_avg_pace: Enhanced avg pace.
        enhanced_avg_speed: Enhanced avg speed.
        enhanced_max_pace: Enhanced max pace.
        enhanced_max_speed: Enhanced max speed.
        enhanced_min_altitude: Enhanced min alt.
        enhanced_max_altitude: Enhanced max alt.
        avg_vertical_ratio: Avg vertical ratio.
        avg_step_length: Average step length.
    """

    start_time: StrictStr
    start_position_lat: StrictFloat | None = None
    start_position_long: StrictFloat | None = None
    end_position_lat: StrictFloat | None = None
    end_position_long: StrictFloat | None = None
    total_elapsed_time: StrictFloat | None = None
    total_timer_time: StrictFloat | None = None
    total_distance: StrictFloat | None = None
    total_cycles: StrictInt | None = None
    total_calories: StrictInt | None = None
    avg_heart_rate: StrictInt | None = None
    max_heart_rate: StrictInt | None = None
    avg_cadence: StrictInt | None = None
    max_cadence: StrictInt | None = None
    avg_power: StrictInt | None = None
    max_power: StrictInt | None = None
    total_ascent: StrictInt | None = None
    total_descent: StrictInt | None = None
    intensity: StrictStr | None = None
    lap_trigger: StrictStr | None = None
    sport: StrictStr | None = None
    sub_sport: StrictStr | None = None
    normalized_power: StrictInt | None = None
    total_work: StrictInt | None = None
    avg_vertical_oscillation: StrictFloat | None = None
    avg_stance_time: StrictFloat | None = None
    avg_fractional_cadence: StrictFloat | None = None
    max_fractional_cadence: StrictFloat | None = None
    enhanced_avg_pace: StrictFloat | None = None
    enhanced_avg_speed: StrictFloat | None = None
    enhanced_max_pace: StrictFloat | None = None
    enhanced_max_speed: StrictFloat | None = None
    enhanced_min_altitude: StrictFloat | None = None
    enhanced_max_altitude: StrictFloat | None = None
    avg_vertical_ratio: StrictFloat | None = None
    avg_step_length: StrictFloat | None = None

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    @field_validator(*_FLOAT_FIELDS, mode="before")
    @classmethod
    def _coerce_decimal_to_float(cls, value: Any) -> Any:
        """
        Coerce ``Decimal`` values from the ORM to ``float``.

        SQLAlchemy returns ``Decimal`` for ``DECIMAL`` columns, but the
        public contract for these fields is ``float``. ``StrictFloat``
        rejects ``Decimal`` outright, so convert at the boundary.

        Args:
            value: Raw value coming from the ORM or API payload.

        Returns:
            ``float`` if a ``Decimal`` was provided, otherwise the value
            unchanged.
        """
        if isinstance(value, Decimal):
            return float(value)
        return value


class ActivityLapsRead(ActivityLapsBase):
    """
    Schema for reading activity laps.

    ``start_time`` crosses the API as a timezone-aware UTC instant, matching the
    parent activity. Clients localize it for display using that activity's
    ``timezone`` — the server no longer ships a pre-formatted wall clock, which
    carried no offset and so could not be converted or round-tripped.

    Attributes:
        id: Lap primary key.
        activity_id: Parent activity ID.
        start_time: Lap start as a timezone-aware UTC instant.
    """

    id: StrictInt
    activity_id: StrictInt
    start_time: datetime  # type: ignore[assignment]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


#: One page of an activity's laps. A lap count has no domain ceiling (a lap per
#: kilometre over an ultra), so the read is paginated rather than returning the
#: whole set — and the shared envelope means it paginates like every other list.
ActivityLapsPage = core_pagination.Page[ActivityLapsRead]
