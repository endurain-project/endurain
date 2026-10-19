"""Domain event channels owned by the activities module.

Channel names (``event_type`` values) are owned by the domain that publishes
them, not by the platform substrate. ``store_activity``
publishes the fact below; any derived work (thumbnail generation today, and
future computations) reacts by subscribing to the same constant, so producer and
subscribers cannot drift on the string. Convention: ``<domain>.<fact>``, past
tense.

The payload *versions* are owned here for the same reason. Bump a model's
``SCHEMA_VERSION`` (and register an upgrader for the step) whenever a field is
renamed, removed, or given a new meaning — a purely additive optional field does
not need one. See :mod:`jasil.event_versioning` for why in-flight events make
this necessary.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict, Field

# Published by ``store_activity`` after an activity (and its streams/laps) has
# been persisted, for every ingestion path (upload, Strava, Garmin, bulk).
ACTIVITY_CREATED = "activity.created"

# Published after an already-stored activity's own columns change: the single
# edit, the bulk visibility edit, and provider gear re-assignment. Derived state
# keyed off those columns (feed/visibility caches, search indexes, live client
# updates) is only reconcilable if the change is a fact someone can subscribe to
# — without it the create/delete events describe an activity's birth and death
# but nothing in between, and every consumer would have to poll.
ACTIVITY_UPDATED = "activity.updated"

# Published by the delete-activity route after the activity row (and its
# DB-cascaded children) has been removed, so each subsystem can clean up the
# artifacts it owns — the map thumbnail today, media/search-index/... later —
# without the route knowing who reacts.
ACTIVITY_DELETED = "activity.deleted"


class ActivityCreatedPayload(VersionedPayload):
    """Validated payload for the ``activity.created`` event.

    Subscribers parse the event through
    :func:`jasil.event_versioning.parse_payload`, so a payload written by another
    build is upgraded or loudly refused instead of being silently misread, and a
    malformed one raises (surfacing via retry / dead-letter) instead of quietly
    marking the job complete.

    Attributes:
        activity_id: The stored activity's ID.
        user_id: The owning user's ID (subscribers load the owner's data).
        duplicate_start_time: Whether the activity duplicated an existing
            activity's start time (marked hidden on store).
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    activity_id: int
    user_id: int
    duplicate_start_time: bool = False


class ActivityDeletedPayload(VersionedPayload):
    """Validated payload for the ``activity.deleted`` event.

    Attributes:
        activity_id: The removed activity's ID.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    activity_id: int


class ActivityUpdatedPayload(VersionedPayload):
    """Validated payload for the ``activity.updated`` event.

    Attributes:
        activity_id: The updated activity's ID.
        user_id: The owning user's ID (subscribers load the owner's data).
        changed_fields: Names of the activity columns this update wrote, sorted.
            Carried so a subscriber can decide whether the change concerns it at
            all — re-rendering a map thumbnail matters when ``hide_map`` flips
            and not when ``private_notes`` does — without re-reading the row and
            diffing it against state it does not keep.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    activity_id: int
    user_id: int | None = None
    changed_fields: list[str] = Field(default_factory=list)
