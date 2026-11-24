"""The process-local registry of websocket connections."""

import asyncio
import uuid

import pytest
from fastapi import WebSocketDisconnect

import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service
from tests._factories.websockets import FakeWebSocket

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
SESSION_1 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e01")
SESSION_2 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e02")


@pytest.fixture
def manager():
    return websocket_manager.WebSocketManager()


class TestRegistry:
    async def test_connecting_accepts_the_socket_and_registers_it(self, manager):
        websocket = FakeWebSocket()

        await manager.connect(USER, SESSION_1, websocket)

        assert websocket.accepted
        assert manager.get_connections(USER) == [websocket]

    async def test_users_are_registered_apart(self, manager):
        first, second = FakeWebSocket(), FakeWebSocket()

        await manager.connect(USER, SESSION_1, first)
        await manager.connect(OTHER_USER, SESSION_1, second)

        assert manager.get_connections(USER) == [first]
        assert manager.get_connections(OTHER_USER) == [second]

    def test_a_user_with_no_connection_has_an_empty_list(self, manager):
        assert manager.get_connections(OTHER_USER) == []

    def test_disconnecting_a_user_that_never_connected_does_nothing(self, manager):
        manager.disconnect(OTHER_USER, FakeWebSocket())

        assert manager.get_connections(OTHER_USER) == []

    async def test_a_second_connection_is_added_beside_the_first(self, manager):
        first, second = FakeWebSocket(), FakeWebSocket()

        await manager.connect(USER, SESSION_1, first)
        await manager.connect(USER, SESSION_1, second)

        assert manager.get_connections(USER) == [first, second]

    async def test_closing_one_tab_keeps_the_other_receiving_hints(self, manager):
        first, second = FakeWebSocket(), FakeWebSocket()
        await manager.connect(USER, SESSION_1, first)
        await manager.connect(USER, SESSION_1, second)

        manager.disconnect(USER, first)
        await websocket_service.deliver_hint(USER, {"k": "v"}, manager)

        assert manager.get_connections(USER) == [second]
        assert second.sent == [{"k": "v"}]
        assert first.sent == []

    async def test_the_last_disconnect_drops_the_user(self, manager):
        websocket = FakeWebSocket()
        await manager.connect(USER, SESSION_1, websocket)

        manager.disconnect(USER, websocket)
        manager.disconnect(USER, websocket)

        assert manager.get_connections(USER) == []

    async def test_the_session_of_a_connection_is_tracked_until_it_leaves(self, manager):
        websocket = FakeWebSocket()
        await manager.connect(USER, SESSION_1, websocket)

        assert manager.get_session_connections(USER, SESSION_1, None) == [websocket]
        manager.disconnect(USER, websocket)

        assert manager.get_session_connections(USER, SESSION_1, None) == []

    def test_the_process_has_one_registry(self):
        assert websocket_manager.get_websocket_manager() is websocket_manager.get_websocket_manager()


class TestEviction:
    """Closing a connection pushed out by a newer one."""

    async def _fill(self, manager, oldest, session_id=SESSION_1):
        await manager.connect(USER, session_id, oldest)
        for _ in range(websocket_manager.MAX_CONNECTIONS_PER_USER):
            await manager.connect(USER, session_id, FakeWebSocket())

    async def test_the_oldest_connection_is_closed_past_the_limit(self, manager):
        oldest = FakeWebSocket()

        await self._fill(manager, oldest)

        assert oldest.closed_with == [websocket_manager.EVICTED_CLOSE_CODE]
        assert oldest not in manager.get_connections(USER)
        assert len(manager.get_connections(USER)) == websocket_manager.MAX_CONNECTIONS_PER_USER

    async def test_an_evicted_connection_is_forgotten_with_its_session(self, manager):
        oldest = FakeWebSocket()

        await self._fill(manager, oldest, SESSION_2)

        assert oldest not in manager.get_session_connections(USER, SESSION_2, None)

    @pytest.mark.parametrize("failure", [WebSocketDisconnect(code=1006), RuntimeError("closed")])
    async def test_a_close_that_fails_does_not_block_the_new_connection(self, manager, failure):
        oldest = FakeWebSocket()
        oldest.close_failure = failure

        await self._fill(manager, oldest)

        assert oldest not in manager.get_connections(USER)
        assert len(manager.get_connections(USER)) == websocket_manager.MAX_CONNECTIONS_PER_USER

    async def test_a_stalled_close_is_given_up_on(self, manager, monkeypatch):
        oldest = FakeWebSocket()
        oldest.stall_closes = True
        monkeypatch.setattr(websocket_manager, "SEND_TIMEOUT_SECONDS", 0.01)

        await asyncio.wait_for(self._fill(manager, oldest), timeout=5)

        assert oldest not in manager.get_connections(USER)

    async def test_an_unexpected_close_error_propagates(self, manager):
        oldest = FakeWebSocket()
        oldest.close_failure = TypeError("bug")

        with pytest.raises(TypeError):
            await self._fill(manager, oldest)


class TestSendIsolation:
    """A failing connection must not stop the others from receiving."""

    async def test_a_stalled_connection_is_given_up_on(self, manager, monkeypatch):
        stalled, healthy = FakeWebSocket(), FakeWebSocket()
        stalled.stall_sends = True
        await manager.connect(USER, SESSION_1, stalled)
        await manager.connect(USER, SESSION_1, healthy)
        monkeypatch.setattr(websocket_manager, "SEND_TIMEOUT_SECONDS", 0.01)

        failures = await websocket_manager.send_json_to_all(manager.get_connections(USER), {"k": "v"})

        assert [socket for socket, _ in failures] == [stalled]
        assert healthy.sent == [{"k": "v"}]

    async def test_a_stalled_connection_is_unregistered_after_a_send(self, manager, monkeypatch):
        stalled, healthy = FakeWebSocket(), FakeWebSocket()
        stalled.stall_sends = True
        await manager.connect(USER, SESSION_1, stalled)
        await manager.connect(USER, SESSION_1, healthy)
        monkeypatch.setattr(websocket_manager, "SEND_TIMEOUT_SECONDS", 0.01)

        await websocket_service.deliver_hint(USER, {"k": "v"}, manager)

        assert manager.get_connections(USER) == [healthy]

    async def test_an_unserializable_payload_keeps_the_connection(self, manager):
        websocket = FakeWebSocket()
        websocket.send_failure = TypeError("not serializable")
        await manager.connect(USER, SESSION_1, websocket)

        await websocket_service.deliver_hint(USER, {"k": object()}, manager)

        assert manager.get_connections(USER) == [websocket]
