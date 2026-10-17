"""Package-owned internal data shapes for activity sets.

Separate from ``schema.py`` (the client-facing set payloads) because these never
reach a client: they carry parsed or archived sets into persistence.
"""

from pydantic import StrictInt

import modules.activities.activity_sets.schema as activity_sets_schema


class ActivitySetsCreate(activity_sets_schema.ActivitySetsBase):
    """A parsed or archived workout set to persist for an activity.

    Attributes:
        activity_id: Parent activity ID.
    """

    activity_id: StrictInt
