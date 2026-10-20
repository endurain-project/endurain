"""Tests for websocket.integration_service module."""

from unittest.mock import AsyncMock, patch

import modules.websocket.integration_service as websocket_integration
import modules.websocket.manager as websocket_manager


async def _push(manager, user_id=1):
    with patch.object(websocket_manager, "get_websocket_manager", return_value=manager):
        return await websocket_integration.push_to_user(user_id, {"message": "hi"})


async def test_a_user_without_a_connection_gets_no_push():
    assert await _push(websocket_manager.WebSocketManager()) is False


async def test_every_connection_of_the_user_receives_the_push():
    manager = websocket_manager.WebSocketManager()
    first, second = AsyncMock(), AsyncMock()
    await manager.connect(1, first)
    await manager.connect(1, second)

    assert await _push(manager) is True
    first.send_json.assert_awaited_once_with({"message": "hi"})
    second.send_json.assert_awaited_once_with({"message": "hi"})


async def test_one_broken_connection_does_not_stop_the_others():
    manager = websocket_manager.WebSocketManager()
    broken, healthy = AsyncMock(), AsyncMock()
    broken.send_json.side_effect = RuntimeError("closed")
    await manager.connect(1, broken)
    await manager.connect(1, healthy)

    assert await _push(manager) is True
    healthy.send_json.assert_awaited_once_with({"message": "hi"})


async def test_the_push_fails_when_every_send_fails():
    manager = websocket_manager.WebSocketManager()
    broken = AsyncMock()
    broken.send_json.side_effect = RuntimeError("closed")
    await manager.connect(1, broken)

    assert await _push(manager) is False
