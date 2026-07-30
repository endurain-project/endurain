"""Single registration surface for the activities domain's event subscribers.

Both entrypoints that need the activities subscribers register them from here:
the API lifespan (:func:`main.startup_event`) and the standalone durable-job
worker (:func:`worker.run_worker_process`). Sharing one list means a subscriber
added for one entrypoint can never silently drift from the other — the failure
mode this module exists to prevent is a durable handler registered in the API
but not the worker (or vice versa), which would leave that subscriber's claimed
jobs unresolvable and dead-lettered on a dedicated worker.

The module also declares each durable subscriber's **reconciliation net** — the
scheduled backfill that re-derives anything the best-effort create path misses
(delivery dropped on the Redis-Streams bus, a provider briefly down, or a direct
:func:`create_activity` that publishes no event, e.g. the profile bulk-restore).
The substrate's non-negotiable rule is that every durable subscriber writing
*durable* derived state ships such a net; declaring the mapping here (rather than
leaving it a comment) lets a test enforce it, so a new subscriber added without a
net — or an exemption reason — fails CI instead of silently losing derived work.
"""

from collections.abc import Callable
from dataclasses import dataclass

import modules.activities.activity.subscribers as activity_subscribers
import modules.activities.activity_file_storage.subscribers as activity_file_storage_subscribers
import modules.activities.activity_geocoding.subscribers as activity_geocoding_subscribers
import modules.activities.activity_ingestion.bulk_import_subscribers as activity_bulk_import_subscribers
import modules.activities.activity_streams.subscribers as activity_streams_subscribers
import modules.activities.activity_thumbnail.service as activity_thumbnail_service
import modules.activities.activity_thumbnail.subscribers as activity_thumbnail_subscribers
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_all_activity_bus_subscribers(events: EventBusProvider) -> None:
    """Register every activities event-bus subscriber on the running bus.

    Called once at startup (the API lifespan) before the event bus is started.
    On the in-process bus these run inline; on the Redis-Streams bus a consumer
    runs them at-least-once. Registration order is preserved for readability but
    carries no semantics — the bus fans an event out to every subscriber of its
    type independently.

    Args:
        events: The event-bus provider to subscribe the handlers on.

    Returns:
        None.
    """
    activity_thumbnail_subscribers.register_thumbnail_subscribers(events)
    activity_subscribers.register_activity_notification_subscribers(events)
    activity_streams_subscribers.register_hr_zone_subscribers(events)
    activity_geocoding_subscribers.register_geocoding_subscribers(events)
    activity_file_storage_subscribers.register_activity_file_cleanup_subscribers(events)


def register_all_activity_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register every activities durable-job handler on the registry.

    Used by **both** the API lifespan and the standalone worker so a handler is
    never registered in one entrypoint but not the other — a mismatch would leave
    the missing subscriber's jobs unresolvable (and dead-lettered) wherever they
    are claimed. Harmless when durable jobs are disabled (the registry is simply
    never consulted).

    Args:
        registry: The durable-subscriber registry to register the handlers on.

    Returns:
        None.
    """
    activity_thumbnail_subscribers.register_thumbnail_durable_handlers(registry)
    activity_subscribers.register_activity_notification_durable_handlers(registry)
    activity_streams_subscribers.register_hr_zone_durable_handlers(registry)
    activity_geocoding_subscribers.register_geocoding_durable_handlers(registry)
    activity_file_storage_subscribers.register_activity_file_cleanup_durable_handlers(registry)
    activity_bulk_import_subscribers.register_bulk_import_durable_handlers(registry)


@dataclass(frozen=True)
class DurableSubscriberNet:
    """A durable subscriber's reconciliation net, or a documented exemption.

    Attributes:
        subscriber_id: The stable durable-subscriber id (as registered on the
            :class:`JobHandlerRegistry`).
        backfill: The scheduled, argument-free backfill that re-derives anything
            the create-path handler missed, or ``None`` when the subscriber is
            exempt (its derived state is transient / self-healing).
        exempt_reason: Why no backfill is required, when ``backfill`` is ``None``.
            Must be set for exempt subscribers and unset otherwise.
    """

    subscriber_id: str
    backfill: Callable[[], None] | None
    exempt_reason: str | None = None


# Single source of truth for the reconciliation-net invariant. Every durable
# subscriber registered by ``register_all_activity_durable_handlers`` must appear
# here exactly once — with a scheduled backfill, or an explicit ``exempt_reason``
# when its derived state is transient (a miss is not durable data loss). The
# invariant test asserts this list matches the registry and that every declared
# backfill is actually scheduled, so drift on either side fails CI.
ACTIVITY_DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_thumbnail_subscribers.THUMBNAIL_GENERATE_SUBSCRIBER_ID,
        activity_thumbnail_service.generate_missing_activity_thumbnails,
    ),
    DurableSubscriberNet(
        activity_streams_subscribers.HR_ZONE_SUBSCRIBER_ID,
        activity_streams_subscribers.run_missing_hr_zone_backfill,
    ),
    DurableSubscriberNet(
        activity_geocoding_subscribers.GEOCODING_SUBSCRIBER_ID,
        activity_geocoding_subscribers.run_missing_location_backfill,
    ),
    DurableSubscriberNet(
        activity_subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Notifications are transient UI signal, not durable state: the activity "
            "row is the source of truth, so a missed new-activity notification "
            "cannot be reconciled after the fact — there is nothing to backfill."
        ),
    ),
    DurableSubscriberNet(
        activity_thumbnail_subscribers.THUMBNAIL_CLEANUP_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Deletion cleanup is an idempotent teardown keyed by activity id; once "
            "the row is gone there is no create-derived state to reconcile. A stray "
            "orphaned thumbnail is harmless (and the create-path thumbnail backfill "
            "only regenerates thumbnails for activities that still exist)."
        ),
    ),
    DurableSubscriberNet(
        activity_file_storage_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Deletion cleanup is an idempotent teardown keyed by activity id; once "
            "the row is gone there is no create-derived state to reconcile. A stray "
            "orphaned source file is harmless (it is never served, only bundled into "
            "a profile export for activities that still exist)."
        ),
    ),
    DurableSubscriberNet(
        activity_bulk_import_subscribers.BULK_IMPORT_FILE_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The durable job IS the reliability mechanism here: each bulk-import file "
            "is its own retryable job that dead-letters (moving the file to the "
            "import-error directory) once its attempts are exhausted. It is a command "
            "job, not an activity.created reaction, so there is no derived state to "
            "re-derive on a schedule — recovering a dead-lettered file means re-adding "
            "it to the bulk-import directory."
        ),
    ),
)
