"""Registration surface and reconciliation declarations for notifications."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.notifications.subscribers as notification_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the notification bus subscribers.

    Args:
        events: The event bus to subscribe on.
    """
    notification_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the notification durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    notification_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
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
    DurableSubscriberNet(
        notification_subscribers.FOLLOWER_REQUEST_REMOVED_NOTIFICATION_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The follow row is the source of truth; clearing its request notification is "
            "an idempotent reaction with no independently reconcilable state."
        ),
    ),
    DurableSubscriberNet(
        notification_subscribers.IDP_LINKED_NOTIFICATION_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The identity-provider link row is the source of truth; its notification is "
            "a transient reaction with no independently reconcilable state."
        ),
    ),
)
