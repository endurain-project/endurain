"""The event envelope, ``new_event`` helper, and standard metadata keys.

Pure module — the single structured shape every event travels in, so the
pipeline can route, trace, correlate, dedup, and retry without knowing the
domain.

Channel names (``event_type`` values) are **owned by the domain that publishes
them**, not defined here — e.g. the activities module owns ``activity.created``.
Keeping them out of the substrate stops this generic layer from accumulating
domain knowledge; a producer and its subscribers import the same domain-side
constant so they cannot drift on the string. Convention: ``<domain>.<fact>`` in
past tense. ``event_type`` stays a plain ``str`` on the envelope so the bus is
open to new events with no edits here.

The envelope is defined ahead of the bus so the wire format never
has to change once the first producer ships.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

# --- Standard metadata keys (correlation context, not domain data) ---
META_REQUEST_ID = "request_id"
META_USER_ID = "user_id"
META_ACTIVITY_ID = "activity_id"


@dataclass(frozen=True)
class Event:
    """Envelope wrapping every event in the system.

    Attributes:
        event_id: UUIDv4 identifying this event instance; stable across retries.
        event_type: Dot-notation channel, e.g. ``activity.created``.
        source: Where the event originated, e.g. ``api:store_activity``.
        timestamp: ISO-8601 UTC timestamp of the first publish (not the retry).
        payload: Domain data, homogeneous per ``event_type``.
        metadata: Correlation context (request_id, user_id, activity_id, ...).
        retry_count: Processing attempts so far; 0 on first publish.
    """

    event_id: str
    event_type: str
    source: str
    timestamp: str
    payload: dict
    metadata: dict = field(default_factory=dict)
    retry_count: int = 0


def new_event(
    event_type: str,
    payload: dict,
    *,
    source: str,
    metadata: dict | None = None,
    event_id: str | None = None,
    retry_count: int = 0,
) -> Event:
    """Mint an :class:`Event`, generating ``event_id`` and ``timestamp``.

    Args:
        event_type: The channel/type, e.g. ``activity.created``.
        payload: Domain data for the event.
        source: Origin label, e.g. ``api:store_activity``.
        metadata: Optional correlation context.
        event_id: Optional explicit id (defaults to a fresh UUIDv4); reuse the
            original id when re-publishing a retry so tracing stays stable.
        retry_count: Attempt counter (incremented on re-publish).

    Returns:
        A frozen :class:`Event` with a fresh id and UTC timestamp.
    """
    return Event(
        event_id=event_id or str(uuid.uuid4()),
        event_type=event_type,
        source=source,
        timestamp=datetime.now(UTC).isoformat(),
        payload=payload,
        metadata=metadata if metadata is not None else {},
        retry_count=retry_count,
    )
