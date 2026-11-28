"""Internal activity contracts: the ingestion seam and the CRUD read projections.

Separate from ``schema.py`` (which holds the API request/response payloads)
because these are **inter-module interfaces**, not HTTP shapes:

* **The ingestion contract** — :class:`ActivityCore`, :class:`ImportSource`,
  :class:`ParsedActivity`. Every ingestion source (the
  file parsers, Strava, Garmin, profile imports) builds this shape, and
  :func:`~modules.activities.activity.ingestion_service.store_parsed_activity`
  persists it without knowing where it came from. This is the seam that makes
  parsing irrelevant to the activities core.
* **CRUD read projections** — the ``*Ref`` dataclasses. Lightweight views CRUD
  hands to a consumer that needs a couple of columns, so an ORM row never leaves
  the persistence layer.

Neither group is ever serialized to a client, so keeping them out of
``schema.py`` also keeps the generated OpenAPI free of internal shapes.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, field_validator, model_validator

import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema


@dataclass(frozen=True)
class ActivityTypeTotals:
    """What the activities of one activity type add up to over a timeframe.

    Summed by the database, so the per-sport stats never load the activities.

    Attributes:
        activity_type: The activity type the totals are for.
        distance: Sum of their distance, in meters.
        time: Sum of their active (timer) time, in seconds.
        calories: Sum of their calories; activities without a value count as zero.
    """

    activity_type: int
    distance: float = 0
    time: float = 0
    calories: float = 0


@dataclass(frozen=True)
class ActivityTotals:
    """What a set of activities adds up to.

    Summed by the database, so a reader that only needs totals (goal progress) never loads the rows.

    Attributes:
        count: How many activities matched.
        calories: Sum of their calories; activities without a value count as zero.
        distance: Sum of their distance, in meters.
        elevation_gain: Sum of their elevation gain, in meters.
        elapsed_time: Sum of their elapsed time, in seconds.
    """

    count: int = 0
    calories: float = 0
    distance: float = 0
    elevation_gain: float = 0
    elapsed_time: float = 0


@dataclass(frozen=True)
class UserProfileActivitySummary:
    """Activity aggregates displayed on a user's profile.

    Attributes:
        week_stats: Visible per-sport totals for the current week.
        month_stats: Visible per-sport totals for the current month.
        month_activity_count: Visible activity count for the current month.
    """

    week_stats: activity_schema.ActivityStatsRead
    month_stats: activity_schema.ActivityStatsRead
    month_activity_count: int


@dataclass(frozen=True)
class ActivityGarminGearRef:
    """Lightweight activity reference for assigning gear from Garmin Connect.

    Attributes:
        id: The activity id.
        garminconnect_gear_id: The Garmin Connect gear UUID the activity carries.
    """

    id: uuid.UUID
    garminconnect_gear_id: str


@dataclass(frozen=True)
class ActivityThumbnailRef:
    """Lightweight activity reference for thumbnail maintenance.

    Carries only the fields the thumbnail subsystem needs (the activity id and
    the stored thumbnail key) so CRUD can hand out this DTO instead of leaking an
    ORM ``Activity`` row.
    """

    id: uuid.UUID
    map_thumbnail_path: str | None = None


@dataclass(frozen=True)
class ActivityLocationRef:
    """Lightweight activity reference for the reverse-geocoding backfill.

    Carries the activity id and its start point so CRUD can hand out this DTO instead of leaking
    an ORM ``Activity`` row when listing activities that still have no resolved
    city/town/country.

    Attributes:
        id: The activity.
        latitude: Latitude of where the activity starts, in degrees.
        longitude: Longitude of where the activity starts, in degrees.
    """

    id: uuid.UUID
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ActivityFeedEntry:
    """A masked feed item paired with its unmasked persistence cursor.

    Attributes:
        activity: Client-facing activity with privacy masking applied.
        cursor_sort_value: Unmasked value the feed orders by: the start time, or the creation time
            where the owner hid the start.
        cursor_id: Raw activity id used to break sort-value ties.
    """

    activity: activity_schema.ActivityRead
    cursor_sort_value: datetime
    cursor_id: uuid.UUID


class ActivityCore(activity_schema.ActivityFields, activity_schema.ActivityHeavyFields):
    """Strict ingestion *input* schema.

    Extends the fields that describe an activity
    (:class:`~modules.activities.activity.schema.ActivityFields` and
    :class:`~modules.activities.activity.schema.ActivityHeavyFields`) — **not** the read
    :class:`~modules.activities.activity.schema.ActivityRead`. That distinction is
    the point: the read model adds the server-owned ``id`` and
    ``map_thumbnail_path``, which a producer must never supply, as would any future
    read-only field.

    Every ingestion producer builds this shape — the file parsers (incl. Garmin's
    ``.fit`` path), the Strava adapter, and the profile bulk-restore. It differs
    from the loose base in two enforced ways:

    * **Owner + start/end are required.** ``user_id`` is required and
      ``start_time``/``end_time`` may not be null — a missing owner or timestamp is
      rejected at construction (the boundary) instead of deep inside
      ``create_activity``.
    * **Times are normalized to UTC-aware at construction.** Parsers emit naive UTC
      wall-clock strings and providers emit ISO strings; the validator coerces both
      to aware UTC at the boundary. Producers pass their string output
      unchanged, while the stored value is always an aware
      ``datetime`` — and unlike the read schema, ``None`` is rejected rather than
      allowed through.

    It also carries the start point of the activity, which the server derives from the samples and never accepts
    from or returns to a client, so it is on this shape alone.

    Attributes:
        start_latitude: Latitude of where the activity starts, in degrees; ``None`` without a position.
        start_longitude: Longitude of where the activity starts, in degrees; ``None`` without a position.
    """

    user_id: uuid.UUID
    # Required (no default): ingestion must provide a start/end time; the validator
    # rejects a null/unparseable value and coerces the rest to aware UTC.
    start_time: datetime
    end_time: datetime
    start_latitude: float | None = Field(default=None, ge=-90, le=90)
    start_longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _require_utc_aware(cls, value: object) -> datetime:
        """Coerce parser/provider datetime output to aware UTC; reject null values.

        Args:
            value: The datetime or ISO string to coerce.

        Returns:
            The aware UTC datetime.

        Raises:
            ValueError: When the value is neither a datetime nor an ISO string.
        """
        if not isinstance(value, datetime | str):
            raise ValueError("must be a valid, non-null datetime")
        return core_timezone.to_utc_aware(value)


@dataclass(frozen=True)
class ImportSource:
    """Provenance of a parsed activity: what identifies it and how far its data is trusted.

    Attributes:
        kind: Origin of the activity (``"upload"`` / ``"bulk_import"`` / ``"garmin"`` / ``"strava"`` /
            ``"reprocess"``), recorded for observability.
        provider_activity_id: The external provider's activity id, when known.
        content_hash: SHA-256 of the parsed file's contents, set by the file ingestion path for sources that carry no
            provider id (upload, bulk import). The ingestion service turns it into the activity's file source, so
            importing the same file again is a no-op. ``None`` for provider syncs, which are identified by their id.
        precedence: How much the source's data is trusted, one of the ``SOURCE_PRECEDENCE_*`` constants.
        retained_file_id: Opaque id of the retained source file row the activity is stored with. The core writes it
            on the activity it creates and on no leg; ``None`` when the source retains no file.
    """

    kind: str
    provider_activity_id: int | None = None
    content_hash: str | None = None
    precedence: int = activity_constants.SOURCE_PRECEDENCE_DEVICE_FILE
    retained_file_id: uuid.UUID | None = None


@dataclass(frozen=True)
class NewSource:
    """One source row to stage with an activity: a single identity, a provider id or a file hash.

    Attributes:
        kind: ``file``, ``garmin`` or ``strava``.
        provider_id: The provider's activity id; set for ``garmin`` and ``strava``.
        file_sha256: The file's SHA-256; set for ``file``.
        session_start: The start of the recording, whole seconds; ``None`` for a whole file (a multisport activity) and
            for a Strava activity.
        precedence: The source's precedence.
    """

    kind: str
    provider_id: int | None
    file_sha256: str | None
    session_start: datetime | None
    precedence: int


@dataclass(frozen=True)
class SourceRead:
    """A stored source row, as the profile export and the tests read it.

    Attributes:
        activity_id: The activity the source belongs to.
        kind: ``file``, ``garmin`` or ``strava``.
        provider_id: The provider's activity id, for ``garmin`` and ``strava``.
        file_sha256: The file's SHA-256, for ``file``.
        session_start: The start of the recording in whole seconds, or ``None``.
        precedence: The source's precedence.
        received_at: When the source reached the activity.
    """

    activity_id: uuid.UUID
    kind: str
    provider_id: int | None
    file_sha256: str | None
    session_start: datetime | None
    precedence: int
    received_at: datetime


class SourceArchiveRecord(BaseModel):
    """A source as the profile archive carries it, with one identity: a provider id or a file hash.

    Attributes:
        activity_id: The id the activity had when the archive was written.
        kind: ``file``, ``garmin`` or ``strava``.
        provider_id: The provider's activity id, for ``garmin`` and ``strava``.
        file_sha256: The file's SHA-256, for ``file``.
        session_start: The start of the recording in whole seconds, or ``None``.
        precedence: The source's precedence.
    """

    activity_id: uuid.UUID
    kind: Literal["file", "garmin", "strava"]
    provider_id: int | None = None
    file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    session_start: datetime | None = None
    precedence: int = Field(ge=0, le=activity_constants.SOURCE_PRECEDENCE_DEVICE_FILE)

    @model_validator(mode="after")
    def _one_identity(self) -> SourceArchiveRecord:
        """Require exactly one of the provider id and the file hash.

        Returns:
            The record.

        Raises:
            ValueError: When both or neither is set.
        """
        if (self.provider_id is None) == (self.file_sha256 is None):
            raise ValueError("a source has exactly one of provider_id and file_sha256")
        return self


class DeletedActivity(NamedTuple):
    """An activity a delete removed, as its ``activity.deleted`` event names it.

    Attributes:
        id: The id the activity had.
        file_id: The retained source file row it referenced, ``None`` for a leg and an activity with no file row.
    """

    id: uuid.UUID
    file_id: uuid.UUID | None


@dataclass
class ParsedActivity:
    """Canonical, format-agnostic parsed activity that the core stores.

    Every ingestion source (the file parsers, Strava, Garmin, profile imports)
    produces this shape; :func:`ingestion_service.store_parsed_activity` persists
    it without any knowledge of where it came from. This is the seam that makes
    parsing irrelevant to the activities core.

    Attributes:
        activity: The strict ``ActivityCore`` input schema to persist.
        components: Parsed child-package data keyed by contributor key.
        source: Where the activity came from.
    """

    activity: ActivityCore
    components: dict[str, object] = field(default_factory=dict)
    source: ImportSource | None = None


@dataclass
class ParsedFile:
    """Everything one activity file yielded — the file parsers' return contract.

    A single file does not always mean a single activity: a multi-session ``.fit``
    holds several, and the ingestion core must not have to know which formats do
    that. Every parser therefore returns this shape, and the core simply iterates
    ``activities``. Before this existed, the core branched on the extension and
    called the FIT-specific split/build helpers itself, which put format knowledge
    back in the one place that is supposed to be format-agnostic.

    Attributes:
        activities: The parsed activities, in file order. Empty when the file held
            nothing importable. A multisport file's legs are here.
        components: Parsed file-scoped package data keyed by contributor key.
        parent: The multisport activity the ``activities`` are the legs of; ``None``
            for every other file.
    """

    activities: list[ParsedActivity] = field(default_factory=list)
    components: dict[str, object] = field(default_factory=dict)
    parent: ParsedActivity | None = None
