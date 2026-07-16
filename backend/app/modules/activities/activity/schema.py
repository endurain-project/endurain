"""Pydantic schemas for activity API payloads."""

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

PositiveInt = Annotated[StrictInt, Field(ge=1)]
VisibilityValue = Annotated[StrictInt, Field(ge=0, le=2)]
LongText = Annotated[StrictStr, Field(max_length=2500)]
ActivityName = Annotated[StrictStr, Field(max_length=250)]


class Activity(BaseModel):
    """
    Schema representing a fitness activity.

    Attributes:
        id: Unique activity identifier.
        user_id: ID of the owning user.
        description: Public activity description.
        private_notes: Private notes visible only to owner.
        distance: Total distance in meters.
        name: Activity name.
        activity_type: Numeric code for the sport type.
        start_time: Activity start time (UTC) — may be a
            pre-formatted string after serialization.
        start_time_tz_applied: Start time with timezone applied.
        end_time: Activity end time (UTC) — may be a
            pre-formatted string after serialization.
        end_time_tz_applied: End time with timezone applied.
        timezone: IANA timezone string.
        total_elapsed_time: Total elapsed wall-clock time in
            seconds.
        total_timer_time: Active timer time in seconds.
        city: City where the activity took place.
        town: Town where the activity took place.
        country: Country where the activity took place.
        created_at: Record creation timestamp (UTC) — may be a
            pre-formatted string after serialization.
        created_at_tz_applied: Creation time with timezone
            applied.
        elevation_gain: Total elevation gain in meters.
        elevation_loss: Total elevation loss in meters.
        pace: Average pace in seconds per kilometer.
        average_speed: Average speed in meters per second.
        max_speed: Maximum speed in meters per second.
        average_power: Average power output in watts.
        max_power: Maximum power output in watts.
        normalized_power: Normalized power in watts.
        average_hr: Average heart rate in bpm.
        max_hr: Maximum heart rate in bpm.
        average_cad: Average cadence in rpm/spm.
        max_cad: Maximum cadence in rpm/spm.
        workout_feeling: Subjective feeling rating (0-100).
        workout_rpe: Rate of perceived exertion (10-100).
        calories: Estimated calories burned.
        visibility: Visibility level of the activity
            (0 - public, 1 - followers, 2 - private).
        gear_id: Associated gear identifier.
        strava_gear_id: Strava gear identifier.
        strava_activity_id: Strava activity identifier.
        garminconnect_activity_id: Garmin Connect activity
            identifier.
        garminconnect_gear_id: Garmin Connect gear identifier.
        import_info: Import metadata (imported, import_source,
            import_ISO_time).
        is_hidden: Whether the activity is hidden.
        hide_start_time: Hide the start time from others.
        hide_location: Hide location data from others.
        hide_map: Hide the map from others.
        hide_hr: Hide heart rate data from others.
        hide_power: Hide power data from others.
        hide_cadence: Hide cadence data from others.
        hide_elevation: Hide elevation data from others.
        hide_speed: Hide speed data from others.
        hide_pace: Hide pace data from others.
        hide_laps: Hide lap data from others.
        hide_workout_sets_steps: Hide workout sets and steps.
        hide_gear: Hide gear information from others.
        tracker_manufacturer: Device manufacturer name.
        tracker_model: Device model name.
        map_thumbnail_path: Path to the map thumbnail image.
        total_cycles: Total number of cycles (e.g., pedal strokes) recorded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(default=None, ge=1)
    user_id: int | None = Field(default=None, ge=1)
    description: str | None = Field(default=None, max_length=2500)
    private_notes: str | None = Field(default=None, max_length=2500)
    distance: int = Field(ge=0)
    name: str = Field(max_length=250)
    activity_type: int = Field(ge=1)
    start_time: datetime | str | None = None
    start_time_tz_applied: str | None = None
    end_time: datetime | str | None = None
    end_time_tz_applied: str | None = None
    timezone: str | None = Field(default=None, max_length=250)
    total_elapsed_time: float | None = Field(default=None, ge=0)
    total_timer_time: float | None = Field(default=None, ge=0)
    city: str | None = Field(default=None, max_length=250)
    town: str | None = Field(default=None, max_length=250)
    country: str | None = Field(default=None, max_length=250)
    created_at: datetime | str | None = None
    created_at_tz_applied: str | None = None
    elevation_gain: int | None = None
    elevation_loss: int | None = None
    pace: float | None = None
    average_speed: float | None = None
    max_speed: float | None = None
    average_power: int | None = None
    max_power: int | None = None
    normalized_power: int | None = None
    average_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    average_cad: int | None = Field(default=None, ge=0)
    max_cad: int | None = Field(default=None, ge=0)
    workout_feeling: int | None = Field(default=None, ge=0, le=100)
    workout_rpe: int | None = Field(default=None, ge=10, le=100)
    calories: int | None = Field(default=None, ge=0)
    visibility: int | None = Field(default=None, ge=0, le=2)
    gear_id: int | None = Field(default=None, ge=1)
    strava_gear_id: str | None = Field(default=None, max_length=45)
    strava_activity_id: int | None = None
    garminconnect_activity_id: int | None = None
    garminconnect_gear_id: str | None = Field(default=None, max_length=45)
    import_info: dict | None = None
    is_hidden: bool = False
    hide_start_time: bool | None = None
    hide_location: bool | None = None
    hide_map: bool | None = None
    hide_hr: bool | None = None
    hide_power: bool | None = None
    hide_cadence: bool | None = None
    hide_elevation: bool | None = None
    hide_speed: bool | None = None
    hide_pace: bool | None = None
    hide_laps: bool | None = None
    hide_workout_sets_steps: bool | None = None
    hide_gear: bool | None = None
    tracker_manufacturer: str | None = Field(default=None, max_length=250)
    tracker_model: str | None = Field(default=None, max_length=250)
    map_thumbnail_path: str | None = Field(default=None, max_length=500)
    total_cycles: int | None = Field(default=None, ge=0)


class ActivitySportStats(BaseModel):
    """
    Aggregated stats for a single sport over a timeframe.

    Attributes:
        distance: Total distance in meters.
        time: Total active time in seconds.
        calories: Total calories burned.
    """

    model_config = ConfigDict(from_attributes=True)

    distance: float = Field(default=0.0, ge=0)
    time: float = Field(default=0.0, ge=0)
    calories: float = Field(default=0.0, ge=0)


class ActivityStats(BaseModel):
    """
    Per-sport aggregated stats for a timeframe (week/month).

    Attributes:
        run: Stats for running activities.
        bike: Stats for cycling activities.
        swim: Stats for swimming activities.
        walk: Stats for walking activities.
        hike: Stats for hiking activities.
        rowing: Stats for rowing activities.
        snow_ski: Stats for snow skiing activities.
        snowboard: Stats for snowboarding activities.
        windsurf: Stats for windsurfing activities.
        stand_up_paddleboarding: Stats for SUP activities.
        surfing: Stats for surfing activities.
        kayaking: Stats for kayaking activities.
        sailing: Stats for sailing activities.
        snowshoeing: Stats for snowshoeing activities.
        inline_skating: Stats for inline skating activities.
    """

    model_config = ConfigDict(from_attributes=True)

    run: ActivitySportStats = Field(default_factory=ActivitySportStats)
    bike: ActivitySportStats = Field(default_factory=ActivitySportStats)
    swim: ActivitySportStats = Field(default_factory=ActivitySportStats)
    walk: ActivitySportStats = Field(default_factory=ActivitySportStats)
    hike: ActivitySportStats = Field(default_factory=ActivitySportStats)
    rowing: ActivitySportStats = Field(default_factory=ActivitySportStats)
    snow_ski: ActivitySportStats = Field(default_factory=ActivitySportStats)
    snowboard: ActivitySportStats = Field(default_factory=ActivitySportStats)
    windsurf: ActivitySportStats = Field(default_factory=ActivitySportStats)
    stand_up_paddleboarding: ActivitySportStats = Field(default_factory=ActivitySportStats)
    surfing: ActivitySportStats = Field(default_factory=ActivitySportStats)
    kayaking: ActivitySportStats = Field(default_factory=ActivitySportStats)
    sailing: ActivitySportStats = Field(default_factory=ActivitySportStats)
    snowshoeing: ActivitySportStats = Field(default_factory=ActivitySportStats)
    inline_skating: ActivitySportStats = Field(default_factory=ActivitySportStats)


class GearActivitiesListResponse(BaseModel):
    """
    Response model for paginated gear activities.

    Attributes:
        total: Total number of activities for gear.
        num_records: Number of records returned.
        page_number: Current page number.
        records: List of activity records.
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    total: int = Field(
        ...,
        ge=0,
        description="Total number of activities for this gear",
    )
    num_records: int | None = Field(
        default=None,
        ge=0,
        description="Number of records returned",
    )
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="Current page number",
    )
    records: list[Activity] = Field(
        default_factory=list,
        description="List of activity records",
    )


class ActivityEdit(BaseModel):
    """
    Schema for partial updates to an activity.

    Attributes:
        id: Activity identifier to update.
        description: Public activity description.
        private_notes: Private notes (owner only).
        name: Activity name.
        activity_type: Numeric sport type code.
        visibility: 0 - public, 1 - followers, 2 - private.
        is_hidden: Whether the activity is hidden.
        gear_id: Associated gear identifier.
        hide_start_time: Hide start time from others.
        hide_location: Hide location from others.
        hide_map: Hide map from others.
        hide_hr: Hide heart rate from others.
        hide_power: Hide power from others.
        hide_cadence: Hide cadence from others.
        hide_elevation: Hide elevation from others.
        hide_speed: Hide speed from others.
        hide_pace: Hide pace from others.
        hide_laps: Hide laps from others.
        hide_workout_sets_steps: Hide workout sets and steps.
        hide_gear: Hide gear from others.
    """

    model_config = ConfigDict(extra="forbid")

    id: PositiveInt
    description: LongText | None = None
    private_notes: LongText | None = None
    name: ActivityName
    activity_type: PositiveInt
    visibility: VisibilityValue | None = None
    is_hidden: StrictBool | None = None
    gear_id: PositiveInt | None = None
    hide_start_time: StrictBool | None = None
    hide_location: StrictBool | None = None
    hide_map: StrictBool | None = None
    hide_hr: StrictBool | None = None
    hide_power: StrictBool | None = None
    hide_cadence: StrictBool | None = None
    hide_elevation: StrictBool | None = None
    hide_speed: StrictBool | None = None
    hide_pace: StrictBool | None = None
    hide_laps: StrictBool | None = None
    hide_workout_sets_steps: StrictBool | None = None
    hide_gear: StrictBool | None = None
