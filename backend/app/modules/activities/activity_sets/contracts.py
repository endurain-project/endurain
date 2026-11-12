"""Package-owned internal data shapes for activity sets.

Separate from ``schema.py`` (the client-facing set payloads) because these never
reach a client: they carry parsed or archived sets into persistence.
"""

import uuid

from pydantic import StrictStr

import modules.activities.activity_sets.schema as activity_sets_schema


class ActivitySetsCreate(activity_sets_schema.ActivitySetsBase):
    """A parsed or archived workout set to persist for an activity.

    Attributes:
        activity_id: Parent activity ID.
        start_time: Set start time ISO string.
    """

    activity_id: uuid.UUID
    start_time: StrictStr
