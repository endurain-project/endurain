"""Activity laps schemas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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
    """Base schema for activity laps: the fields a stored lap and a read lap share.

    Attributes:
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

    start_position_lat: StrictFloat | None = Field(default=None, description="Start latitude in decimal degrees")
    start_position_long: StrictFloat | None = Field(default=None, description="Start longitude in decimal degrees")
    end_position_lat: StrictFloat | None = Field(default=None, description="End latitude in decimal degrees")
    end_position_long: StrictFloat | None = Field(default=None, description="End longitude in decimal degrees")
    total_elapsed_time: StrictFloat | None = Field(default=None, description="Elapsed time of the lap in seconds")
    total_timer_time: StrictFloat | None = Field(default=None, description="Timer time of the lap in seconds")
    total_distance: StrictFloat | None = Field(default=None, description="Distance of the lap in meters")
    total_cycles: StrictInt | None = Field(
        default=None, description="Number of cycles in the lap, such as pedal strokes or strides"
    )
    total_calories: StrictInt | None = Field(default=None, description="Energy burned in the lap in kilocalories")
    avg_heart_rate: StrictInt | None = Field(default=None, description="Average heart rate in beats per minute")
    max_heart_rate: StrictInt | None = Field(default=None, description="Maximum heart rate in beats per minute")
    avg_cadence: StrictInt | None = Field(
        default=None, description="Average cadence in revolutions per minute (steps per minute for running)"
    )
    max_cadence: StrictInt | None = Field(
        default=None, description="Maximum cadence in revolutions per minute (steps per minute for running)"
    )
    avg_power: StrictInt | None = Field(default=None, description="Average power in watts")
    max_power: StrictInt | None = Field(default=None, description="Maximum power in watts")
    total_ascent: StrictInt | None = Field(default=None, description="Elevation gained in the lap in meters")
    total_descent: StrictInt | None = Field(default=None, description="Elevation lost in the lap in meters")
    intensity: StrictStr | None = None
    lap_trigger: StrictStr | None = None
    sport: StrictStr | None = None
    sub_sport: StrictStr | None = None
    normalized_power: StrictInt | None = Field(default=None, description="Normalized power in watts")
    total_work: StrictInt | None = Field(default=None, description="Work done in the lap in joules")
    avg_vertical_oscillation: StrictFloat | None = Field(
        default=None, description="Average vertical oscillation in millimeters"
    )
    avg_stance_time: StrictFloat | None = Field(default=None, description="Average ground contact time in milliseconds")
    avg_fractional_cadence: StrictFloat | None = Field(
        default=None, description="Fractional part of the average cadence in revolutions per minute"
    )
    max_fractional_cadence: StrictFloat | None = Field(
        default=None, description="Fractional part of the maximum cadence in revolutions per minute"
    )
    enhanced_avg_pace: StrictFloat | None = Field(default=None, description="Average pace in seconds per meter")
    enhanced_avg_speed: StrictFloat | None = Field(default=None, description="Average speed in meters per second")
    enhanced_max_pace: StrictFloat | None = Field(default=None, description="Best pace in seconds per meter")
    enhanced_max_speed: StrictFloat | None = Field(default=None, description="Maximum speed in meters per second")
    enhanced_min_altitude: StrictFloat | None = Field(default=None, description="Lowest altitude in meters")
    enhanced_max_altitude: StrictFloat | None = Field(default=None, description="Highest altitude in meters")
    avg_vertical_ratio: StrictFloat | None = Field(default=None, description="Average vertical ratio as a percentage")
    avg_step_length: StrictFloat | None = Field(default=None, description="Average step length in millimeters")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    @field_validator(*_FLOAT_FIELDS, mode="before")
    @classmethod
    def _coerce_decimal_to_float(cls, value: object) -> object:
        """Coerce ``Decimal`` values from the ORM to ``float``.

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


class ActivityLapsCreate(ActivityLapsBase):
    """A parsed or archived lap to persist for an activity.

    Attributes:
        start_time: Lap start time ISO string.
    """

    start_time: StrictStr


class ActivityLapsRead(ActivityLapsBase):
    """Schema for reading activity laps.

    ``start_time`` crosses the API as a timezone-aware UTC instant, matching the
    parent activity. Clients localize it for display using that activity's
    ``timezone``; a pre-formatted wall clock would carry no offset and so could
    not be converted or round-tripped.

    Attributes:
        id: Lap primary key.
        activity_id: Parent activity ID.
        start_time: Lap start as a timezone-aware UTC instant, or None when the
            parent hides its start time from this viewer.
    """

    id: uuid.UUID
    activity_id: uuid.UUID
    start_time: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


#: One page of an activity's laps. A lap count has no domain ceiling (a lap per
#: kilometre over an ultra), so the read is paginated rather than returning the
#: whole set — and the shared envelope means it paginates like every other list.
ActivityLapsPage = core_pagination.Page[ActivityLapsRead]
