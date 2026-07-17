"""Domain event channels owned by the activities module.

Channel names (``event_type`` values) are owned by the domain that publishes
them, not by the platform substrate (foundations plan §8). ``store_activity``
publishes the fact below; any derived work (thumbnail generation today, and
future computations) reacts by subscribing to the same constant, so producer and
subscribers cannot drift on the string. Convention: ``<domain>.<fact>``, past
tense.
"""

# Published by ``store_activity`` after an activity (and its streams/laps) has
# been persisted, for every ingestion path (upload, Strava, Garmin, bulk).
ACTIVITY_CREATED = "activity.created"

# Published by the delete-activity route after the activity row (and its
# DB-cascaded children) has been removed, so each subsystem can clean up the
# artifacts it owns — the map thumbnail today, media/search-index/... later —
# without the route knowing who reacts.
ACTIVITY_DELETED = "activity.deleted"

# Published by the edit-activity route after an activity's metadata has been
# updated, so subscribers can react to edits (reindex, feed refresh, ...) without
# the route knowing who reacts. The payload carries the changed field names.
ACTIVITY_UPDATED = "activity.updated"
