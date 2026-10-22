"""Receives realtime hints on this process and pushes them to the sockets it holds."""

import core.async_bridge as core_async_bridge
import core.logger as core_logger
import modules.websocket.keys as websocket_keys
import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service

logger = core_logger.get_logger(__name__)


def on_realtime_hint(key: str, hint: dict) -> None:
    """Handle one hint from the realtime channel.

    Every started process receives every hint, so most are for a user whose socket is
    held elsewhere and are dropped on the loop. The channel is server-wide, so a key that does
    not address a user is ignored. This runs on the channel's subscriber thread (inline
    on the publisher for the in-process channel), so the send is handed to the main
    event loop, which owns the sockets.

    Args:
        key: The audience the hint was published for.
        hint: The hint to push.
    """
    user_id = websocket_keys.parse_user_key(key)
    if user_id is None:
        logger.debug("Ignored a realtime hint that does not address a user")
        return
    # The registry belongs to the event loop, so whether this process holds the user's
    # socket is answered there (deliver_hint returns at once when it does not).
    core_async_bridge.dispatch(websocket_service.deliver_hint(user_id, hint, websocket_manager.get_websocket_manager()))
