"""The single publish seam every producer goes through.

One tiny facade so no producer ever assembles an :class:`~infra.events.Event`
or touches the active platform directly. Centralising publishing here means the
transactional outbox (foundations plan F8) is a change to *this* function alone,
not to every call site.

It resolves the active platform, stamps the ambient request id for correlation,
and mints the envelope. Delivery then takes one of two routes:

* **Durable (outbox):** when durable jobs are enabled, the caller supplies its DB
  session, and the event type has registered durable subscribers, the event is
  written to the ``event_outbox`` — the relay later fans it out into retryable
  per-subscriber jobs. The event is also recorded ``queued`` in ``event_log`` so
  the observability dashboard reflects durable events too (execution detail then
  lives in the Jobs dashboard).
* **Best-effort (bus):** otherwise the event is dispatched through the event bus
  (inline in ``local``, via Redis Streams in ``distributed``), which records the
  full lifecycle itself.

**Delivery guarantee.** The producer's domain row is the source of truth; this
publish is *best-effort* from the producer's perspective — failures are logged and
swallowed so publishing never breaks the producer's own work. The outbox is not
committed in the same transaction as the domain change (the ingestion path commits
per-CRUD), so a crash between the domain commit and the outbox write can drop an
event. Every subscriber must therefore have a reconciliation net — a backfill or
sweeper that re-derives missed work (the thumbnail subsystem's hourly backfill is
the reference). A future unit-of-work refactor can upgrade this to a genuinely
atomic outbox; until then, "durable" means *retryable once written*, not *never
lost*. Channel names and payload shape stay owned by the publishing domain; this
layer only knows the generic envelope.
"""

from typing import Any

import core.config as core_config
import core.logger as core_logger
import core.middleware_request_id as core_middleware_request_id
import infra.jobs.outbox as jobs_outbox
import infra.jobs.registry as jobs_registry
import infra.runtime as platform_runtime
from infra.events import META_REQUEST_ID, new_event


def publish(
    event_type: str,
    payload: dict,
    *,
    source: str,
    metadata: dict | None = None,
    db: Any = None,
) -> None:
    """Publish a domain event through the active platform, best-effort.

    Args:
        event_type: The domain-owned channel, e.g. ``activity.created``.
        payload: Domain data for the event (homogeneous per ``event_type``).
        source: Origin label, e.g. ``api:store_activity``.
        metadata: Optional correlation context; merged with the ambient request
            id when one is set on the current request.
        db: The producer's SQLAlchemy session. When provided and durable jobs are
            enabled for this event type, the event is written to the outbox using
            this session (durable delivery); otherwise it is ignored.

    Returns:
        None. Delivery failures are logged and swallowed so a publish never
        breaks the producer. The domain row remains the source of truth and each
        subscriber's reconciliation net recovers anything missed.
    """
    try:
        platform = platform_runtime.get_active_platform()
        merged: dict = {}
        request_id = core_middleware_request_id.get_request_id()
        if request_id:
            merged[META_REQUEST_ID] = request_id
        if metadata:
            merged.update(metadata)
        event = new_event(event_type, payload, source=source, metadata=merged)
        if db is not None and _durable_delivery_enabled(event_type):
            # Record a terminal 'queued' row so durable events stay visible in the
            # event_log dashboard without counting as perpetually pending (the bus
            # records its own lifecycle; the outbox path does not go through the
            # bus). Per-subscriber execution is tracked in the Jobs dashboard.
            if platform.recorder is not None:
                platform.recorder.record_queued(event)
            jobs_outbox.add_to_outbox(event, now=platform.clock.now(), db=db)
        else:
            platform.events.publish(event)
    except Exception as err:
        core_logger.print_to_log(
            f"Failed to publish event {event_type}: {err}",
            "error",
            exc=err,
        )


def _durable_delivery_enabled(event_type: str) -> bool:
    """Whether an event type should be delivered durably (outbox -> jobs).

    True only when durable jobs are switched on and at least one durable
    subscriber is registered for the event type; otherwise the best-effort bus
    path is used.
    """
    return core_config.settings.JOBS_ENABLED and bool(jobs_registry.registry.subscribers_for(event_type))
