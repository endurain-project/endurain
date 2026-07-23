"""Pydantic schemas for activity API payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)

import core.timezone as core_timezone

if TYPE_CHECKING:
    # Imported for typing only: a runtime import would be circular (the sub-module
    # packages import activity.crud, which imports this module). These name the
    # element types of the ingestion contract's child collections (ParsedActivity).
    import modules.activities.activity_sets.schema as activity_sets_schema
    import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

PositiveInt = Annotated[StrictInt, Field(ge=1)]
VisibilityValue = Annotated[StrictInt, Field(ge=0, le=2)]
LongText = Annotated[StrictStr, Field(max_length=2500)]
ActivityName = Annotated[StrictStr, Field(max_length=250)]


@dataclass(frozen=True)
class ActivityThumbnailRef:
    """Lightweight activity reference for thumbnail maintenance.

    Carries only the fields the thumbnail subsystem needs (the activity id and
    the stored thumbnail key) so CRUD can hand out this DTO instead of leaking an
    ORM ``Activity`` row.
    """

    id: int
    map_thumbnail_path: str | None = None


@dataclass(frozen=True)
class ActivityLocationRef:
    """Lightweight activity reference for the reverse-geocoding backfill.

    Carries only the activity id so CRUD can hand out this DTO instead of leaking
    an ORM ``Activity`` row when listing activities that still have no resolved
    city/town/country.
    """

    id: int


@dataclass(frozen=True)
class ActivityMigrationRef:
    """Lightweight activity projection for data-backfill migrations.

    Carries only the identity, owner, provider ids, and time bounds the backfill
    migrations read (they never mutate the row), so CRUD can hand out this DTO
    instead of leaking an ORM ``Activity`` row when a migration iterates every
    activity.

    Attributes:
        id: Activity id.
        user_id: Owning user id.
        start_time: Activity start (timezone-aware UTC).
        end_time: Activity end (timezone-aware UTC).
        strava_activity_id: Strava provider id, when imported from Strava.
        garminconnect_activity_id: Garmin Connect provider id, when applicable.
    """

    id: int
    user_id: int
    start_time: datetime
    end_time: datetime
    strava_activity_id: int | None = None
    garminconnect_activity_id: int | None = None


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


class ActivityCore(Activity):
    """Strict ingestion *input* schema.

    The tightened variant of the read :class:`Activity` that every ingestion
    producer builds — the file parsers (incl. Garmin's ``.fit`` path), the Strava
    adapter, and the profile bulk-restore. It differs from the loose read schema in
    two enforced ways:

    * **Owner + start/end are required.** ``user_id`` is required and
      ``start_time``/``end_time`` may not be null — a missing owner or timestamp is
      rejected at construction (the boundary) instead of deep inside
      ``create_activity``.
    * **Times are normalized to UTC-aware at construction.** Parsers emit naive UTC
      wall-clock strings and providers emit ISO strings; the validator coerces both
      to aware UTC, relocating the normalization that used to run late in
      ``ParsedActivity.__post_init__``. The field type stays ``datetime | str |
      None`` so producers keep passing their string output unchanged (no call-site
      churn), while the stored value is always an aware ``datetime``.
    """

    user_id: int = Field(ge=1)
    # Required (no default): ingestion must provide a start/end time; the validator
    # rejects a null/unparseable value and coerces the rest to aware UTC.
    start_time: datetime | str | None
    end_time: datetime | str | None

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _require_utc_aware(cls, value: Any) -> datetime:
        """Coerce parser/provider datetime output to aware UTC; reject null values."""
        aware = core_timezone.to_utc_aware(value)
        if aware is None:
            raise ValueError("must be a valid, non-null datetime")
        return aware


@dataclass(frozen=True)
class ParsedStream:
    """A single parsed activity stream (type + waypoints), before persistence.

    Carries no ``activity_id`` — that is assigned by the core when the activity
    row is created (see :func:`ingestion_service.store_parsed_activity`).
    """

    stream_type: int
    stream_waypoints: list


@dataclass(frozen=True)
class ImportSource:
    """Provenance of a parsed activity, recorded for observability.

    Attributes:
        kind: Origin of the activity (``"upload"`` / ``"bulk_import"`` /
            ``"garmin"``).
        provider_activity_id: The external provider's activity id, when known.
        dedup_key: Explicit stable idempotency key for the activity. When set and
            an activity with the same key already exists for the owner,
            re-ingestion is a no-op instead of creating a duplicate. When absent,
            the ingestion service derives one (provider id, else file
            ``content_hash`` + start time), falling back to start-time dedup.
        content_hash: SHA-256 of the parsed file's contents, set by the file
            ingestion path for provider-less sources (upload / bulk import). The
            ingestion service turns it into a ``file:{hash}:{start}`` dedup key so
            re-importing the exact same file is a true no-op. ``None`` for
            provider syncs (they key off the provider id).
    """

    kind: str
    provider_activity_id: int | None = None
    dedup_key: str | None = None
    content_hash: str | None = None


@dataclass
class ParsedActivity:
    """Canonical, format-agnostic parsed activity that the core stores.

    Every ingestion source (the file parsers, Strava, Garmin, profile imports)
    produces this shape; :func:`ingestion_service.store_parsed_activity` persists
    it without any knowledge of where it came from. This is the seam that makes
    parsing irrelevant to the activities core.

    Attributes:
        activity: The strict ``ActivityCore`` input schema to persist.
        streams: Parsed streams (type + waypoints), assigned an ``activity_id``
            at persist time.
        laps: Optional parsed laps — dicts keyed by the ``ActivityLapsBase`` field
            names — passed through to ``create_activity_laps`` unchanged.
        sets: Optional parsed workout sets (validated ``ActivitySetsCreate``
            schemas, or the raw positional lists the FIT parser emits).
        workout_steps: Optional parsed workout steps (validated
            ``ActivityWorkoutSteps`` schemas).
        source: Where the activity came from.
    """

    activity: ActivityCore
    streams: list[ParsedStream] = field(default_factory=list)
    laps: list[dict[str, Any]] | None = None
    sets: list[activity_sets_schema.ActivitySetsCreate | list] | None = None
    workout_steps: list[activity_workout_steps_schema.ActivityWorkoutSteps] | None = None
    source: ImportSource | None = None
