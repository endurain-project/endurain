"""Registers the websocket module's bus and realtime subscribers."""

from jasil.providers import EventBusProvider, RealtimeProvider

import modules.websocket.subscribers as websocket_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the websocket event consumers on the running bus.

    Args:
        events: The event bus to subscribe on.
    """
    websocket_subscribers.register_bus_subscribers(events)


def register_realtime_subscribers(realtime: RealtimeProvider) -> None:
    """Subscribe this process to the realtime hint channel.

    Only a process that holds websockets calls this (the API); the job worker only
    publishes and never subscribes. The caller starts the channel afterwards.

    Args:
        realtime: The platform's realtime provider.
    """
    realtime.subscribe(websocket_subscribers.on_realtime_hint)
