"""Durable command registration for the users module."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry

import modules.users.users.scheduled_jobs as users_scheduled_jobs
import modules.users.users.subscribers as users_subscribers


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the users command handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    users_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        users_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID,
        users_scheduled_jobs.requeue_stalled_deletions,
    ),
)
