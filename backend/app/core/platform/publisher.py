"""The single publish seam every producer goes through.

One tiny facade so no producer ever assembles an :class:`~core.platform.events.Event`
or touches the active platform directly. Centralising publishing here means the
future transactional outbox (foundations plan F8 — write the event to a durable
store inside the producer's DB transaction, deliver after commit) is a change to
*this* function alone, not to every call site.

Today it resolves the active platform, stamps the ambient request id for
correlation, mints the envelope, and publishes best-effort — publishing must
never break the producer's own work, so delivery failures are logged and
swallowed (the domain's DB row remains the source of truth). Channel names and
payload shape stay owned by the publishing domain; this layer only knows the
generic envelope.
"""

import core.logger as core_logger
import core.middleware_request_id as core_middleware_request_id
import core.platform.runtime as platform_runtime
from core.platform.events import META_REQUEST_ID, new_event


def publish(
    event_type: str,
    payload: dict,
    *,
    source: str,
    metadata: dict | None = None,
) -> None:
    """Publish a domain event through the active platform, best-effort.

    Args:
        event_type: The domain-owned channel, e.g. ``activity.created``.
        payload: Domain data for the event (homogeneous per ``event_type``).
        source: Origin label, e.g. ``api:store_activity``.
        metadata: Optional correlation context; merged with the ambient request
            id when one is set on the current request.

    Returns:
        None. Delivery failures are logged and swallowed so a publish never
        breaks the producer.
    """
    try:
        platform = platform_runtime.get_active_platform()
        merged: dict = {}
        request_id = core_middleware_request_id.get_request_id()
        if request_id:
            merged[META_REQUEST_ID] = request_id
        if metadata:
            merged.update(metadata)
        platform.events.publish(new_event(event_type, payload, source=source, metadata=merged))
    except Exception as err:
        core_logger.print_to_log(
            f"Failed to publish event {event_type}: {err}",
            "error",
            exc=err,
        )
