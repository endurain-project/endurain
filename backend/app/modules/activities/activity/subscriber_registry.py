"""Durable command registration for the activity package."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry

import modules.activities.activity.subscribers as activity_subscribers


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the activity command handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    activity_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_subscribers.VISIBILITY_EDIT_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The activities' stored visibility is the source of truth and the edit only touches rows that "
            "still differ, so the user asks again; a stuck claim expires after an hour."
        ),
    ),
)
