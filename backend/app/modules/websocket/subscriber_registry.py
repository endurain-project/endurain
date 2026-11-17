"""Registers the websocket module's bus, durable and realtime subscribers."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider, RealtimeProvider

import modules.websocket.subscribers as websocket_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the websocket event consumers on the running bus.

    Args:
        events: The event bus to subscribe on.
    """
    websocket_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the websocket durable handlers.

    Args:
        registry: The durable job handler registry.
    """
    websocket_subscribers.register_durable_handlers(registry)


def register_realtime_subscribers(realtime: RealtimeProvider) -> None:
    """Subscribe this process to the realtime hint channel.

    Only a process that holds websockets calls this (the API); the job worker only
    publishes and never subscribes. The caller starts the channel afterwards.

    Args:
        realtime: The platform's realtime provider.
    """
    realtime.subscribe(websocket_subscribers.on_realtime_hint)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        websocket_subscribers.CLOSE_SOCKETS_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A missed close cannot be backfilled: the revocation holds no record of which sockets were open, "
            "and every socket ends at its lifetime cap."
        ),
    ),
)
