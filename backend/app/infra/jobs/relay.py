"""The outbox relay — turns published events into per-subscriber durable jobs.

Runs on every replica (scheduled): ``list_unrelayed`` claims a batch with
``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent relayers take disjoint rows
without a single-runner lock. For each unrelayed outbox row it enqueues one job
per durable subscriber of the event type and stamps the row relayed. The fan-out
is idempotent (jobs dedup on ``event_id + subscriber_id``), so a crash between
enqueue and stamping — or any overlap between relayers — simply re-relays
harmlessly on the next pass.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

import infra.jobs.crud as jobs_crud
import infra.jobs.outbox as jobs_outbox
from infra.events import Event
from infra.jobs.models import EventOutbox
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import ClockProvider


@dataclass(frozen=True)
class _OutboxSnapshot:
    id: str
    event_id: str
    event_type: str
    source: str
    timestamp: str
    payload: dict
    metadata: dict | None


def relay_outbox_once(
    *,
    registry: JobHandlerRegistry,
    clock: ClockProvider,
    session_factory: Callable[[], Session],
    max_attempts: int,
    batch_size: int,
) -> int:
    """
    Relay one batch of unrelayed outbox rows into durable jobs.

    Args:
        registry: The durable-subscriber registry (event type -> subscribers).
        clock: Time source for job/outbox timestamps.
        session_factory: Opens a fresh session per unit of work.
        max_attempts: Attempt ceiling stamped on each enqueued job.
        batch_size: Maximum number of outbox rows to relay in this pass.

    Returns:
        The number of outbox rows relayed.
    """
    with session_factory() as db:
        snapshots = [_snapshot(row) for row in jobs_outbox.list_unrelayed(limit=batch_size, db=db)]
    for snapshot in snapshots:
        event = _event_from(snapshot)
        with session_factory() as db:
            for subscriber_id in registry.subscribers_for(event.event_type):
                jobs_crud.enqueue_job(event, subscriber_id, max_attempts=max_attempts, now=clock.now(), db=db)
            jobs_outbox.mark_relayed(snapshot.id, now=clock.now(), db=db)
    return len(snapshots)


def _event_from(snapshot: _OutboxSnapshot) -> Event:
    return Event(
        event_id=snapshot.event_id,
        event_type=snapshot.event_type,
        source=snapshot.source,
        timestamp=snapshot.timestamp,
        payload=snapshot.payload,
        metadata=snapshot.metadata or {},
        retry_count=0,
    )


def _snapshot(row: EventOutbox) -> _OutboxSnapshot:
    return _OutboxSnapshot(
        id=row.id,
        event_id=row.event_id,
        event_type=row.event_type,
        source=row.source,
        timestamp=row.timestamp,
        payload=dict(row.payload),
        metadata=dict(row.event_metadata) if row.event_metadata else None,
    )
