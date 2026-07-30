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

Payload versioning
------------------
``schema_version`` describes the shape of ``payload`` for its ``event_type``. It
lives on the envelope rather than inside each payload dict so the substrate can
carry it without parsing domain data, and so no producer can forget it.

It exists because the code that *writes* a payload and the code that *reads* it
are not guaranteed to be the same version: a durable event is staged in the
outbox, relayed on a schedule, retried with backoff, and may sit dead-lettered
indefinitely — and during a rolling deploy old and new replicas run at once. A
consumer that silently ignores unknown keys (every payload model sets
``extra="ignore"``) would read a renamed or repurposed field as its default and
do the wrong thing quietly. The version turns that into something a consumer can
detect: see :mod:`infra.event_versioning`.

The number is owned by the publishing domain, like the channel name. Bump it in
the domain's publisher when the payload's shape or a field's meaning changes;
purely additive optional fields do not need a bump.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

# --- Standard metadata keys (correlation context, not domain data) ---
META_REQUEST_ID = "request_id"
META_USER_ID = "user_id"
META_ACTIVITY_ID = "activity_id"

#: Version assumed for an event that carries none — every event written before
#: ``schema_version`` existed. Persisted rows default to this on read.
INITIAL_SCHEMA_VERSION = 1


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
        schema_version: Which version of ``payload``'s shape this event carries,
            owned by the publishing domain. Defaults to
            :data:`INITIAL_SCHEMA_VERSION` so existing producers are unchanged.
    """

    event_id: str
    event_type: str
    source: str
    timestamp: str
    payload: dict
    metadata: dict = field(default_factory=dict)
    retry_count: int = 0
    schema_version: int = INITIAL_SCHEMA_VERSION


def new_event(
    event_type: str,
    payload: dict,
    *,
    source: str,
    metadata: dict | None = None,
    event_id: str | None = None,
    retry_count: int = 0,
    schema_version: int = INITIAL_SCHEMA_VERSION,
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
        schema_version: The payload-shape version this producer writes.

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
        schema_version=schema_version,
    )
