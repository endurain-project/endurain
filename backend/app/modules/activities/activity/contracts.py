"""Internal activity contracts: the ingestion seam and the CRUD read projections.

Separate from ``schema.py`` (which holds the API request/response payloads)
because these are **inter-module interfaces**, not HTTP shapes:

* **The ingestion contract** — :class:`ActivityCore`, :class:`ParsedStream`,
  :class:`ImportSource`, :class:`ParsedActivity`. Every ingestion source (the
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
from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator

import core.timezone as core_timezone
from modules.activities.activity.schema import Activity

if TYPE_CHECKING:
    # Imported for typing only: a runtime import would be circular (the sub-module
    # packages import activity.crud, which imports this module). These name the
    # element types of the ingestion contract's child collections (ParsedActivity,
    # ParsedFile).
    import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
    import modules.activities.activity_sets.schema as activity_sets_schema
    import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema


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


class ActivityCore(Activity):
    """Strict ingestion *input* schema.

    The tightened variant of the read :class:`~modules.activities.activity.schema.Activity`
    that every ingestion producer builds — the file parsers (incl. Garmin's ``.fit``
    path), the Strava adapter, and the profile bulk-restore. It differs from the loose
    read schema in two enforced ways:

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
        exercise_titles: File-scoped exercise-title reference rows (FIT strength
            workouts). They belong to the *file* rather than to any one activity,
            so they are carried here and persisted once, before the activities.
    """

    activities: list[ParsedActivity] = field(default_factory=list)
    exercise_titles: list[activity_exercise_titles_schema.ActivityExerciseTitles] | None = None
