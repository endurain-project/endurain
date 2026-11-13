"""Tests for websocket.subscribers and subscriber_registry."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from jasil.backends.realtime_inprocess import InProcessRealtime
from jasil.events import new_event

import modules.websocket.keys as websocket_keys
import modules.websocket.manager as websocket_manager
import modules.websocket.subscriber_registry as websocket_subscriber_registry
import modules.websocket.subscribers as websocket_subscribers

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")


async def _hold(manager, user_id=USER):
    websocket = AsyncMock()
    await manager.connect(user_id, "s1", websocket)
    return websocket


class TestOnRealtimeHint:
    async def test_a_hint_for_a_user_held_here_is_handed_to_the_main_loop(self):
        manager = websocket_manager.WebSocketManager()
        await _hold(manager, USER)

        with (
            patch.object(websocket_manager, "get_websocket_manager", return_value=manager),
            patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch,
        ):
            websocket_subscribers.on_realtime_hint(websocket_keys.user_key(USER), {"message": "hi"})

        dispatch.assert_called_once()
        dispatch.call_args.args[0].close()

    async def test_a_hint_for_a_user_held_elsewhere_is_dropped_on_the_loop(self):
        manager = websocket_manager.WebSocketManager()

        with (
            patch.object(websocket_manager, "get_websocket_manager", return_value=manager),
            patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch,
        ):
            websocket_subscribers.on_realtime_hint(websocket_keys.user_key(USER), {"message": "hi"})

        assert await dispatch.call_args.args[0] is False

    def test_a_key_that_does_not_address_a_user_is_ignored(self):
        with patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch:
            websocket_subscribers.on_realtime_hint(f"device:{USER}", {"message": "hi"})
            websocket_subscribers.on_realtime_hint("user:abc", {"message": "hi"})

        dispatch.assert_not_called()


class TestControlMessages:
    async def test_a_control_message_closes_sockets_and_is_never_sent_as_a_hint(self):
        manager = websocket_manager.WebSocketManager()
        websocket = await _hold(manager, USER)

        with (
            patch.object(websocket_manager, "get_websocket_manager", return_value=manager),
            patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch,
        ):
            websocket_subscribers.on_realtime_hint(
                websocket_keys.control_key(USER), {"session_id": "s1", "except_session_id": None}
            )

        await dispatch.call_args.args[0]
        websocket.close.assert_awaited_once_with(code=websocket_manager.SESSION_ENDED_CLOSE_CODE)
        websocket.send_json.assert_not_awaited()

    def test_a_malformed_control_message_is_ignored(self):
        with patch.object(websocket_subscribers.core_async_bridge, "dispatch") as dispatch:
            websocket_subscribers.on_realtime_hint(websocket_keys.control_key(USER), {"session_id": 5})

        dispatch.assert_not_called()

    def test_control_and_user_keys_do_not_address_each_other(self):
        assert websocket_keys.parse_user_key(websocket_keys.control_key(USER)) is None
        assert websocket_keys.parse_control_key(websocket_keys.user_key(USER)) is None
        assert websocket_keys.parse_control_key("control:abc") is None


class TestSessionsRevokedEvent:
    @staticmethod
    def _event(**payload):
        import modules.auth.sessions.events as sessions_events

        return new_event(sessions_events.SESSIONS_REVOKED, {"user_id": str(USER), **payload}, source="test")

    def test_the_event_reaches_every_replica_through_the_realtime_channel(self):
        realtime = InProcessRealtime()
        received = []
        realtime.subscribe(lambda key, hint: received.append((key, hint)))
        realtime.start()
        platform = MagicMock(realtime=realtime)

        with (
            patch.object(websocket_subscribers.platform_runtime, "is_platform_active", return_value=True),
            patch.object(websocket_subscribers.platform_runtime, "get_active_platform", return_value=platform),
        ):
            websocket_subscribers.close_sockets_for_event(self._event(session_id="s1"))

        assert received == [(websocket_keys.control_key(USER), {"session_id": "s1", "except_session_id": None})]

    def test_the_registry_subscribes_the_event(self):
        import modules.auth.sessions.events as sessions_events

        events = MagicMock()

        websocket_subscriber_registry.register_bus_subscribers(events)

        events.subscribe.assert_called_once_with(
            sessions_events.SESSIONS_REVOKED, websocket_subscribers.on_sessions_revoked_close_sockets
        )


def test_the_registry_subscribes_the_handler_to_the_channel():
    realtime = MagicMock(spec=InProcessRealtime)

    websocket_subscriber_registry.register_realtime_subscribers(realtime)

    realtime.subscribe.assert_called_once_with(websocket_subscribers.on_realtime_hint)
