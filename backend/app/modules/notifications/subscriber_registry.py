"""Registration surface and reconciliation declarations for notifications."""

import modules.notifications.subscribers as notification_subscribers
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_all_notification_bus_subscribers(events: EventBusProvider) -> None:
    """Register every notification bus subscriber."""
    notification_subscribers.register_notification_subscribers(events)


def register_all_notification_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register every notification durable handler."""
    notification_subscribers.register_notification_durable_handlers(registry)


NOTIFICATION_DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        notification_subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Notifications are transient UI signals, not activity-derived durable "
            "state. The activity row remains the source of truth."
        ),
    ),
    DurableSubscriberNet(
        notification_subscribers.FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The follow row is the source of truth; a request notification is a "
            "transient reaction with no independently reconcilable state."
        ),
    ),
    DurableSubscriberNet(
        notification_subscribers.FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The accepted follow row is the source of truth; its notification is "
            "a transient reaction with no independently reconcilable state."
        ),
    ),
)
