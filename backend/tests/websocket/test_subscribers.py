"""Realtime hints and revocations reaching the sockets this process holds, through the platform channels."""

import asyncio
import uuid

import jasil.runtime as jasil_runtime
import pytest
from jasil.events import new_event
from jasil.jobs.registry import JobHandlerRegistry

import core.async_bridge as core_async_bridge
import modules.auth.sessions.events as sessions_events
import modules.websocket.integration_service as websocket_integration
import modules.websocket.keys as websocket_keys
import modules.websocket.manager as websocket_manager
import modules.websocket.subscriber_registry as websocket_subscriber_registry
import modules.websocket.subscribers as websocket_subscribers
from tests._factories.websockets import FakeWebSocket

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
SESSION_1 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e01")
SESSION_2 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e02")


@pytest.fixture(autouse=True)
def _fresh_registry():
    websocket_manager.get_websocket_manager.cache_clear()
    yield
    websocket_manager.get_websocket_manager.cache_clear()


@pytest.fixture
def realtime():
    """The platform's realtime channel with this module subscribed, as the API process subscribes it."""
    channel = jasil_runtime.get_active_platform().realtime
    websocket_subscriber_registry.register_realtime_subscribers(channel)
    return channel


@pytest.fixture
async def main_loop():
    """Make the running test loop the process's main loop, as the lifespan does for the API."""
    core_async_bridge.capture_running_loop()
    yield
    core_async_bridge.set_main_loop(None)


async def _hold(user_id=USER, session_id=SESSION_1):
    websocket = FakeWebSocket()
    await websocket_manager.get_websocket_manager().connect(user_id, session_id, websocket)
    return websocket


class TestRealtimeHints:
    async def test_a_hint_for_a_user_held_here_is_pushed_to_every_socket_of_the_user(self, realtime, main_loop):
        first, second = await _hold(), await _hold()
        bystander = await _hold(OTHER_USER)

        websocket_integration.push_to_user(USER, {"message": "hi"})
        await asyncio.wait_for(asyncio.gather(first.received.wait(), second.received.wait()), timeout=5)

        assert first.sent == second.sent == [{"message": "hi"}]
        assert bystander.sent == []

    async def test_a_hint_for_a_user_held_elsewhere_reaches_no_socket(self, realtime, main_loop):
        bystander = await _hold(OTHER_USER)

        websocket_integration.push_to_user(USER, {"message": "hi"})
        websocket_integration.push_to_user(OTHER_USER, {"message": "sentinel"})
        await asyncio.wait_for(bystander.received.wait(), timeout=5)

        assert bystander.sent == [{"message": "sentinel"}]

    async def test_a_key_that_does_not_address_a_user_is_ignored(self, realtime, main_loop):
        websocket = await _hold()

        realtime.notify(f"device:{USER}", {"message": "hi"})
        realtime.notify("user:abc", {"message": "hi"})
        websocket_integration.push_to_user(USER, {"message": "sentinel"})
        await asyncio.wait_for(websocket.received.wait(), timeout=5)

        assert websocket.sent == [{"message": "sentinel"}]


class TestControlMessages:
    async def test_a_control_message_closes_sockets_and_is_never_sent_as_a_hint(self, realtime, main_loop):
        websocket = await _hold()

        realtime.notify(websocket_keys.control_key(USER), {"session_id": str(SESSION_1), "except_session_id": None})
        await _closed(websocket)

        assert websocket.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]
        assert websocket.sent == []

    async def test_a_control_message_without_a_session_closes_every_socket_but_the_excepted_one(
        self, realtime, main_loop
    ):
        kept, closed = await _hold(session_id=SESSION_1), await _hold(session_id=SESSION_2)

        realtime.notify(websocket_keys.control_key(USER), {"session_id": None, "except_session_id": str(SESSION_1)})
        await _closed(closed)

        assert kept.closed_with == []
        assert closed.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]

    @pytest.mark.parametrize("message", [{"session_id": 5}, {"session_id": "s1"}, {"except_session_id": ["x"]}])
    async def test_a_malformed_control_message_closes_nothing(self, realtime, main_loop, message):
        websocket = await _hold()

        realtime.notify(websocket_keys.control_key(USER), message)
        websocket_integration.push_to_user(USER, {"message": "sentinel"})
        await asyncio.wait_for(websocket.received.wait(), timeout=5)

        assert websocket.closed_with == []

    def test_control_and_user_keys_do_not_address_each_other(self):
        assert websocket_keys.parse_user_key(websocket_keys.control_key(USER)) is None
        assert websocket_keys.parse_control_key(websocket_keys.user_key(USER)) is None
        assert websocket_keys.parse_control_key("control:abc") is None


async def _closed(websocket):
    """Wait until the loop has closed a socket."""
    await asyncio.wait_for(websocket.closed.wait(), timeout=5)


class TestSessionsRevokedEvent:
    @staticmethod
    def _event(**payload):
        return new_event(sessions_events.SESSIONS_REVOKED, {"user_id": str(USER), **payload}, source="test")

    async def test_the_event_closes_the_sockets_of_the_revoked_session_through_the_realtime_channel(
        self, realtime, main_loop
    ):
        websocket_subscriber_registry.register_bus_subscribers(jasil_runtime.get_active_platform().events)
        revoked, other_session = await _hold(session_id=SESSION_1), await _hold(session_id=SESSION_2)

        jasil_runtime.get_active_platform().events.publish(self._event(session_id=str(SESSION_1)))
        await _closed(revoked)

        assert revoked.closed_with == [websocket_manager.SESSION_ENDED_CLOSE_CODE]
        assert other_session.closed_with == []

    def test_the_event_is_announced_to_every_replica_as_a_control_message(self):
        received = []
        jasil_runtime.get_active_platform().realtime.subscribe(lambda key, hint: received.append((key, hint)))

        websocket_subscribers.close_sockets_for_event(self._event(session_id=str(SESSION_1)))

        assert received == [
            (websocket_keys.control_key(USER), {"session_id": str(SESSION_1), "except_session_id": None})
        ]

    def test_the_event_is_dropped_when_no_platform_is_running(self):
        import jasil.testing as jasil_testing

        jasil_testing.reset_all()

        websocket_subscribers.close_sockets_for_event(self._event(session_id=str(SESSION_1)))

    def test_a_durable_run_of_the_event_closes_sockets_the_same_way(self):
        registry = JobHandlerRegistry()
        websocket_subscriber_registry.register_durable_handlers(registry)
        received = []
        jasil_runtime.get_active_platform().realtime.subscribe(lambda key, hint: received.append((key, hint)))

        handler = registry.get(websocket_subscribers.CLOSE_SOCKETS_SUBSCRIBER_ID)
        handler(self._event(except_session_id=str(SESSION_2)))

        assert received == [
            (websocket_keys.control_key(USER), {"session_id": None, "except_session_id": str(SESSION_2)})
        ]
        assert registry.subscribers_for(sessions_events.SESSIONS_REVOKED) == (
            websocket_subscribers.CLOSE_SOCKETS_SUBSCRIBER_ID,
        )

    def test_the_durable_subscriber_has_an_exempt_net(self):
        nets = {net.subscriber_id: net for net in websocket_subscriber_registry.DURABLE_SUBSCRIBER_NETS}

        net = nets[websocket_subscribers.CLOSE_SOCKETS_SUBSCRIBER_ID]
        assert net.backfill is None
        assert net.exempt_reason
