"""Tests for websocket.subscribers and subscriber_registry."""

from unittest.mock import AsyncMock, MagicMock, patch

from jasil.backends.realtime_inprocess import InProcessRealtime

import modules.websocket.keys as websocket_keys
import modules.websocket.manager as websocket_manager
import modules.websocket.subscriber_registry as websocket_subscriber_registry
import modules.websocket.subscribers as websocket_subscribers


async def _hold(manager, user_id=1):
    websocket = AsyncMock()
    await manager.connect(user_id, websocket)
    return websocket


class TestOnRealtimeHint:
    async def test_a_hint_for_a_user_held_here_is_handed_to_the_main_loop(self):
        manager = websocket_manager.WebSocketManager()
        await _hold(manager, 7)

        with (
            patch.object(websocket_manager, "get_websocket_manager", return_value=manager),
            patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch,
        ):
            websocket_subscribers.on_realtime_hint(websocket_keys.user_key(7), {"message": "hi"})

        dispatch.assert_called_once()
        dispatch.call_args.args[0].close()

    async def test_a_hint_for_a_user_held_elsewhere_is_dropped_on_the_loop(self):
        manager = websocket_manager.WebSocketManager()

        with (
            patch.object(websocket_manager, "get_websocket_manager", return_value=manager),
            patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch,
        ):
            websocket_subscribers.on_realtime_hint(websocket_keys.user_key(7), {"message": "hi"})

        assert await dispatch.call_args.args[0] is False

    def test_a_key_that_does_not_address_a_user_is_ignored(self):
        with patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch:
            websocket_subscribers.on_realtime_hint("device:7", {"message": "hi"})
            websocket_subscribers.on_realtime_hint("user:abc", {"message": "hi"})

        dispatch.assert_not_called()


def test_the_registry_subscribes_the_handler_to_the_channel():
    realtime = MagicMock(spec=InProcessRealtime)

    websocket_subscriber_registry.register_realtime_subscribers(realtime)

    realtime.subscribe.assert_called_once_with(websocket_subscribers.on_realtime_hint)
