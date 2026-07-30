"""Domain event channels owned by the activities module.

Channel names (``event_type`` values) are owned by the domain that publishes
them, not by the platform substrate. ``store_activity``
publishes the fact below; any derived work (thumbnail generation today, and
future computations) reacts by subscribing to the same constant, so producer and
subscribers cannot drift on the string. Convention: ``<domain>.<fact>``, past
tense.
"""

from pydantic import BaseModel, ConfigDict

# Published by ``store_activity`` after an activity (and its streams/laps) has
# been persisted, for every ingestion path (upload, Strava, Garmin, bulk).
ACTIVITY_CREATED = "activity.created"

# Published by the delete-activity route after the activity row (and its
# DB-cascaded children) has been removed, so each subsystem can clean up the
# artifacts it owns — the map thumbnail today, media/search-index/... later —
# without the route knowing who reacts.
ACTIVITY_DELETED = "activity.deleted"


class ActivityCreatedPayload(BaseModel):
    """Validated payload for the ``activity.created`` event.

    Durable subscribers validate the event payload against this schema, so a
    malformed payload raises (surfacing via retry / dead-letter) instead of
    silently marking the job complete.

    Attributes:
        activity_id: The stored activity's ID.
        user_id: The owning user's ID (subscribers load the owner's data).
        duplicate_start_time: Whether the activity duplicated an existing
            activity's start time (marked hidden on store).
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: int
    user_id: int
    duplicate_start_time: bool = False


class ActivityDeletedPayload(BaseModel):
    """Validated payload for the ``activity.deleted`` event.

    Attributes:
        activity_id: The removed activity's ID.
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: int
