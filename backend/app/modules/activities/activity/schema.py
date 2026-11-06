"""Pydantic schemas for activity API request/response payloads.

Internal shapes — the ingestion contract (``ParsedActivity`` and friends) and the
CRUD read projections (the ``*Ref`` DTOs) — live in ``contracts.py`` so this module
stays exactly what the API serializes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)

import core.pagination as core_pagination
import core.partial_update as core_partial_update
import core.timezone as core_timezone
import core.types as core_types
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.constants as activity_constants
import modules.users.users.schema as users_schema

#: The activity type of a stored row or an ingestion producer, which hand over the stored integer. A request
#: field is the plain enum instead, which refuses the integer.
StoredActivityType = Annotated[
    activity_constants.ActivityType, BeforeValidator(activity_constants.ActivityType.accept_stored)
]
#: The media type of a stored row, which hands over the stored integer.
StoredMediaType = Annotated[activity_constants.MediaType, BeforeValidator(activity_constants.MediaType.accept_stored)]
#: The visibility of a stored row or an ingestion producer, which hand over the stored integer.
StoredActivityVisibility = Annotated[
    activity_constants.ActivityVisibility, BeforeValidator(activity_constants.ActivityVisibility.accept_stored)
]
LongText = Annotated[StrictStr, Field(max_length=2500)]
ActivityName = core_types.DisplayName


class ActivityBase(BaseModel):
    """The fields that describe an activity, shared by the read and write shapes.

    Split out from :class:`Activity` so the ingestion contract
    (:class:`~modules.activities.activity.contracts.ActivityCore`) can extend
    *this* rather than the read model. Inheriting from the read model would make
    every field added for the API a valid ingestion input — including server-owned
    ones like ``id`` and ``map_thumbnail_path``, which a producer must never be
    able to set. The two shapes share their common ground explicitly and each
    adds only what it owns.

    Attributes:
        user_id: ID of the owning user.
        description: Public activity description.
        private_notes: Private notes visible only to owner.
        distance: Total distance in meters.
        name: Activity name.
        activity_type: The sport type.
        start_time: Activity start as a timezone-aware UTC instant.
        end_time: Activity end as a timezone-aware UTC instant.
        timezone: IANA timezone the activity was recorded in. Clients render
            ``start_time``/``end_time`` in this zone to show the athlete's
            local wall clock.
        total_elapsed_time: Total elapsed wall-clock time in
            seconds.
        total_timer_time: Active timer time in seconds.
        city: City where the activity took place.
        town: Town where the activity took place.
        country: Country where the activity took place.
        created_at: Record creation as a timezone-aware UTC instant.
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
        total_cycles: Total number of cycles (e.g., pedal strokes) recorded.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    user_id: core_types.RecordId | None = None
    description: str | None = Field(default=None, max_length=2500)
    private_notes: str | None = Field(default=None, max_length=2500)
    distance: int = Field(ge=0)
    name: str = Field(max_length=250)
    activity_type: StoredActivityType
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: str | None = Field(default=None, max_length=250)
    total_elapsed_time: float | None = Field(default=None, ge=0)
    total_timer_time: float | None = Field(default=None, ge=0)
    city: str | None = Field(default=None, max_length=250)
    town: str | None = Field(default=None, max_length=250)
    country: str | None = Field(default=None, max_length=250)
    created_at: datetime | None = None
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
    visibility: StoredActivityVisibility | None = None
    gear_id: core_types.RecordId | None = None
    strava_gear_id: str | None = Field(default=None, max_length=45)
    strava_activity_id: int | None = None
    garminconnect_activity_id: int | None = None
    garminconnect_gear_id: str | None = Field(default=None, max_length=45)
    import_info: dict[str, Any] | None = None
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
    total_cycles: int | None = Field(default=None, ge=0)

    @field_validator("timezone", mode="after")
    @classmethod
    def _canonicalize_timezone(cls, value: str | None) -> str | None:
        """Store a legacy timezone alias under its canonical IANA name.

        Args:
            value: The timezone name, or None.

        Returns:
            The canonical name.
        """
        return core_timezone.canonical(value)

    @field_validator("start_time", "end_time", "created_at", mode="before")
    @classmethod
    def _normalize_to_utc_aware(cls, value: object) -> object:
        """Accept the ingestion producers' ISO strings, expose an aware UTC datetime.

        The field type is ``datetime | None`` so the API promises a ``date-time``
        and generated clients type a timestamp as one, not as ``string | Date``.
        This pre-validator keeps every producer working by normalizing whatever
        it passes (naive UTC wall clock from the file parsers, offset-carrying
        ISO strings from the providers) to an aware UTC instant.

        Args:
            value: An ISO string or datetime.

        Returns:
            The aware UTC datetime, or the input unchanged when it is not a date.
        """
        return core_timezone.to_utc_aware(value) if isinstance(value, str) else value


class ActivityMediaEmbedded(BaseModel):
    """A photo of an activity, as embedded in an activity list response.

    The activity media package extends this with the same fields for its own endpoints, so
    the root package declares the shape it embeds without importing that package.

    Attributes:
        id: Media record identifier.
        activity_id: The activity the photo belongs to.
        media_type: Media kind.
        url: Signed, servable address of the photo.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: StrictInt = Field(ge=1)
    activity_id: StrictInt = Field(ge=1)
    media_type: StoredMediaType
    url: str = Field(min_length=1)


class ActivityRead(ActivityBase):
    """Schema representing a stored fitness activity — what the API returns.

    Extends :class:`ActivityBase` with the fields the **server** owns: they are
    read out of a stored row and are never accepted from an ingestion producer,
    which is exactly why they live here rather than on the shared base.

    Attributes:
        id: Unique activity identifier, assigned on insert.
        map_thumbnail_path: Storage key of the generated map thumbnail, written
            by the thumbnail subsystem reacting to ``activity.created``. Server-side
            only: it is excluded from serialization, so a client never receives it.
        map_thumbnail_url: The servable, token-gated URL of the thumbnail, set by
            the service layer for a viewer allowed to see the map.
        media: The activity's photos with signed URLs, set by the service layer on list
            responses for the viewer's own activities and empty otherwise.
    """

    id: int = Field(ge=1)
    map_thumbnail_path: str | None = Field(default=None, max_length=500, exclude=True)
    map_thumbnail_url: str | None = None
    version: int | None = Field(default=None, ge=1)
    media: list[ActivityMediaEmbedded] = Field(
        default_factory=list,
        description="The activity's photos, set on list responses for the viewer's own activities",
    )


class ActivitySportStats(BaseModel):
    """Aggregated stats for a single sport over a timeframe.

    Attributes:
        distance: Total distance in meters.
        time: Total active time in seconds.
        calories: Total calories burned.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    distance: float = Field(default=0.0, ge=0)
    time: float = Field(default=0.0, ge=0)
    calories: float = Field(default=0.0, ge=0)


class ActivityStatsRead(BaseModel):
    """Per-sport aggregated stats for a timeframe (week/month).

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

    model_config = ConfigDict(from_attributes=True, extra="forbid")

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


#: One page of activities. Aliases the shared :class:`core.pagination.Page` so
#: the activities list endpoints and every other module's return the same
#: envelope rather than each inventing its own.
ActivityPage = core_pagination.Page[ActivityRead]


class ActivityFeedPage(core_pagination.CursorPage[ActivityRead]):
    """One keyset slice of the following feed.

    The feed takes inserts at the head continuously, so offset paging would repeat and skip rows
    across requests.

    Attributes:
        users: The public profile of each owner on this slice, keyed by user ID, one entry per
            owner however many of their activities the slice holds. It is the projection
            ``GET /users/id/{user_id}`` returns, so the client needs no lookup per owner. An owner
            who is inactive or awaiting approval has no entry.
    """

    users: dict[int, users_schema.UserPublicRead] = Field(
        default_factory=dict,
        description="Public profile of each activity owner on this slice, keyed by user ID",
    )


class ActivitiesBulkEditStatus(BaseModel):
    """Where a queued bulk edit across a user's activities is.

    Attributes:
        status: Lifecycle state of the edit.
    """

    status: bulk_edit_constants.BulkEditStatus = Field(..., description="Lifecycle state of the bulk edit")

    model_config = ConfigDict(extra="forbid")


class ActivitiesBulkEdit(core_partial_update.NotClearable):
    """Schema for a bulk (PATCH) update across the caller's own activities.

    Every field is optional and only the fields present in the request body are
    applied, so adding a second bulk-editable attribute later does not need a
    new endpoint. Unknown fields are rejected (``extra="forbid"``) rather than
    silently ignored, which is what stops a typo'd field from looking like a
    successful no-op.

    Attributes:
        visibility: Visibility to apply to every activity the caller owns.
    """

    model_config = ConfigDict(extra="forbid")

    not_clearable = ("visibility",)

    visibility: activity_constants.ActivityVisibility | None = None


class ActivityEdit(core_partial_update.NotClearable, BaseModel):
    """Schema for partial (PATCH) updates to an activity.

    Every field is optional: only the fields present in the request body are
    applied (``exclude_unset``), and unknown fields are rejected
    (``extra="forbid"``). The activity id comes from the path, not the body.

    Attributes:
        description: Public activity description.
        private_notes: Private notes (owner only).
        name: Activity name.
        activity_type: The sport type.
        visibility: Who may see the activity.
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

    not_clearable = (
        "name",
        "activity_type",
        "visibility",
        "is_hidden",
        "hide_start_time",
        "hide_location",
        "hide_map",
        "hide_hr",
        "hide_power",
        "hide_cadence",
        "hide_elevation",
        "hide_speed",
        "hide_pace",
        "hide_laps",
        "hide_workout_sets_steps",
        "hide_gear",
    )

    model_config = ConfigDict(extra="forbid")

    description: LongText | None = None
    private_notes: LongText | None = None
    name: ActivityName | None = None
    activity_type: activity_constants.ActivityType | None = None
    visibility: activity_constants.ActivityVisibility | None = None
    is_hidden: StrictBool | None = None
    gear_id: core_types.RecordId | None = None
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
