"""Package-owned internal data shapes for activity streams.

Separate from ``schema.py`` (the client-facing stream payloads) because these
never reach a client. They carry parser output into generic activity ingestion.
"""

from dataclasses import dataclass

import modules.activities.activity_streams.schema as activity_streams_schema


@dataclass(frozen=True)
class ParsedStream:
    """A parsed stream before its parent activity identifier is assigned."""

    stream_type: int
    stream_waypoints: list


class ActivityStreamsCreate(activity_streams_schema.ActivityStreamsBase):
    """A parsed or archived stream to persist for an activity.

    Inherits all fields from ``ActivityStreamsBase``. Internal: it never reaches
    a client, so it is not part of ``schema``.
    """
