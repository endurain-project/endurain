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

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import Field, field_validator

import core.timezone as core_timezone
from modules.activities.activity.schema import Activity, ActivityBase


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
class ActivityScoringContext:
    """Parent columns required to score one activity's streams."""

    activity_id: int
    owner_id: int
    total_timer_time: float | None = None


@dataclass(frozen=True)
class ActivityFeedEntry:
    """A masked feed item paired with its unmasked persistence cursor.

    Attributes:
        activity: Client-facing activity with privacy masking applied.
        cursor_start_time: Raw start time used by the feed ordering.
        cursor_id: Raw activity id used to break start-time ties.
    """

    activity: Activity
    cursor_start_time: datetime
    cursor_id: int


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


@dataclass(frozen=True)
class ActivityUsageTotals:
    """Distance and moving time accumulated by a set of activities.

    Returned to the gears module so it can report how much a gear (or one of its
    components) has been used without querying the activities table itself.

    Attributes:
        distance: Total distance in meters.
        time: Total moving time in seconds.
    """

    distance: float = 0.0
    time: float = 0.0


@dataclass(frozen=True)
class GearUsageWindow:
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


class ActivityCore(ActivityBase):
    """Strict ingestion *input* schema.

    Extends :class:`~modules.activities.activity.schema.ActivityBase` — the
    fields that describe an activity — **not** the read
    :class:`~modules.activities.activity.schema.Activity`. That distinction is
    the point: the read model adds the server-owned ``id`` and
    ``map_thumbnail_path``, and while this class inherited from it those became
    accepted ingestion inputs by accident, as would every future read-only field.

    Every ingestion producer builds this shape — the file parsers (incl. Garmin's
    ``.fit`` path), the Strava adapter, and the profile bulk-restore. It differs
    from the loose base in two enforced ways:

    * **Owner + start/end are required.** ``user_id`` is required and
      ``start_time``/``end_time`` may not be null — a missing owner or timestamp is
      rejected at construction (the boundary) instead of deep inside
      ``create_activity``.
    * **Times are normalized to UTC-aware at construction.** Parsers emit naive UTC
      wall-clock strings and providers emit ISO strings; the validator coerces both
      to aware UTC, relocating the normalization that used to run late in
      ``ParsedActivity.__post_init__``. Producers keep passing their string output
      unchanged (no call-site churn), while the stored value is always an aware
      ``datetime`` — and unlike the read schema, ``None`` is rejected rather than
      allowed through.
    """

    user_id: int = Field(ge=1)
    # Required (no default): ingestion must provide a start/end time; the validator
    # rejects a null/unparseable value and coerces the rest to aware UTC.
    start_time: datetime
    end_time: datetime

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _require_utc_aware(cls, value: Any) -> datetime:
        """Coerce parser/provider datetime output to aware UTC; reject null values."""
        aware = core_timezone.to_utc_aware(value)
        if aware is None:
            raise ValueError("must be a valid, non-null datetime")
        return aware


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
        components: Parsed child-package data keyed by contributor key.
        source: Where the activity came from.
    """

    activity: ActivityCore
    components: dict[str, Any] = field(default_factory=dict)
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
            nothing importable.
        components: Parsed file-scoped package data keyed by contributor key.
    """

    activities: list[ParsedActivity] = field(default_factory=list)
    components: dict[str, Any] = field(default_factory=dict)
