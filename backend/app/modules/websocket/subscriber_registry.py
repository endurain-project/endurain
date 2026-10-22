"""Registers the websocket module's realtime subscriber."""

from jasil.providers import RealtimeProvider

import modules.websocket.subscribers as websocket_subscribers


def register_realtime_subscribers(realtime: RealtimeProvider) -> None:
    """Subscribe this process to the realtime hint channel.

    Only a process that holds websockets calls this (the API); the job worker only
    publishes and never subscribes. The caller starts the channel afterwards.

    Args:
        realtime: The platform's realtime provider.
    """
    realtime.subscribe(websocket_subscribers.on_realtime_hint)
