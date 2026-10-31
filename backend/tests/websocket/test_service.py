"""Tests for websocket.service module."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service


async def _manager_with(*connections, user_id=1):
    manager = websocket_manager.WebSocketManager()
    for connection in connections:
        await manager.connect(user_id, connection)
    return manager


class TestDeliverHint:
    async def test_a_user_without_a_connection_gets_no_push(self):
        manager = websocket_manager.WebSocketManager()

        assert await websocket_service.deliver_hint(1, {"message": "hi"}, manager) is False

    async def test_every_connection_of_the_user_receives_the_hint(self):
        first, second = AsyncMock(), AsyncMock()
        manager = await _manager_with(first, second)

        assert await websocket_service.deliver_hint(1, {"message": "hi"}, manager) is True
        first.send_json.assert_awaited_once_with({"message": "hi"})
        second.send_json.assert_awaited_once_with({"message": "hi"})

    async def test_one_broken_connection_does_not_stop_the_others_and_is_dropped(self):
        broken, healthy = AsyncMock(), AsyncMock()
        broken.send_json.side_effect = RuntimeError("closed")
        manager = await _manager_with(broken, healthy)

        assert await websocket_service.deliver_hint(1, {"message": "hi"}, manager) is True
        healthy.send_json.assert_awaited_once_with({"message": "hi"})
        assert manager.get_connections(1) == [healthy]

    async def test_the_hint_fails_when_every_send_fails(self):
        broken = AsyncMock()
        broken.send_json.side_effect = RuntimeError("closed")
        manager = await _manager_with(broken)

        assert await websocket_service.deliver_hint(1, {"message": "hi"}, manager) is False


class TestServeConnection:
    async def test_the_connection_is_registered_while_served_and_removed_after(self):
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()
        seen = []

        async def receive():
            seen.append(manager.get_connections(1))
            raise WebSocketDisconnect()

        websocket.receive.side_effect = receive

        await websocket_service.serve_connection(websocket, 1, manager)

        assert seen == [[websocket]]
        assert manager.get_connections(1) == []

    @pytest.mark.parametrize("frame", [{"text": "not json"}, {"bytes": b"\x00"}])
    async def test_a_data_frame_closes_the_connection(self, frame):
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()
        websocket.receive.side_effect = [{"type": "websocket.receive", **frame}]

        await websocket_service.serve_connection(websocket, 1, manager)

        websocket.close.assert_awaited_once_with(code=1008)
        assert manager.get_connections(1) == []

    async def test_a_connection_is_closed_once_it_is_too_old(self, monkeypatch):
        monkeypatch.setattr(websocket_service, "MAX_CONNECTION_SECONDS", 0.01)
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()

        async def receive():
            await asyncio.sleep(1)

        websocket.receive.side_effect = receive

        await websocket_service.serve_connection(websocket, 1, manager)

        websocket.close.assert_awaited_once_with(code=1001)
        assert manager.get_connections(1) == []

    async def test_the_connection_is_removed_however_the_loop_ends(self):
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()
        websocket.receive.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await websocket_service.serve_connection(websocket, 1, manager)

        assert manager.get_connections(1) == []
