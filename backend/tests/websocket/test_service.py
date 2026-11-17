"""Tests for websocket.service module."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect

import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
SESSION_1 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e01")
SESSION_2 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e02")


async def _manager_with(*connections, user_id=USER):
    manager = websocket_manager.WebSocketManager()
    for connection in connections:
        await manager.connect(user_id, SESSION_1, connection)
    return manager


class TestCloseRevokedConnections:
    async def _two_sessions(self):
        mine, other, someone_else = AsyncMock(), AsyncMock(), AsyncMock()
        manager = websocket_manager.WebSocketManager()
        await manager.connect(USER, SESSION_1, mine)
        await manager.connect(USER, SESSION_2, other)
        await manager.connect(OTHER_USER, SESSION_1, someone_else)
        return manager, mine, other, someone_else

    async def test_a_revoked_session_closes_only_its_own_sockets(self):
        manager, mine, other, someone_else = await self._two_sessions()

        await websocket_service.close_revoked_connections(USER, SESSION_1, None, manager)

        mine.close.assert_awaited_once_with(code=websocket_manager.SESSION_ENDED_CLOSE_CODE)
        other.close.assert_not_awaited()
        someone_else.close.assert_not_awaited()
        assert manager.get_connections(USER) == [other]

    async def test_a_user_wide_revocation_closes_every_socket_of_the_user(self):
        manager, mine, other, someone_else = await self._two_sessions()

        await websocket_service.close_revoked_connections(USER, None, None, manager)

        mine.close.assert_awaited_once_with(code=websocket_manager.SESSION_ENDED_CLOSE_CODE)
        other.close.assert_awaited_once_with(code=websocket_manager.SESSION_ENDED_CLOSE_CODE)
        someone_else.close.assert_not_awaited()
        assert manager.get_connections(USER) == []

    async def test_revoking_the_other_sessions_keeps_the_current_one(self):
        manager, mine, other, _ = await self._two_sessions()

        await websocket_service.close_revoked_connections(USER, None, SESSION_1, manager)

        mine.close.assert_not_awaited()
        other.close.assert_awaited_once_with(code=websocket_manager.SESSION_ENDED_CLOSE_CODE)

    async def test_a_socket_that_cannot_be_closed_does_not_stop_the_others(self):
        manager, mine, other, _ = await self._two_sessions()
        mine.close.side_effect = RuntimeError("closed")

        await websocket_service.close_revoked_connections(USER, None, None, manager)

        other.close.assert_awaited_once()
        assert manager.get_connections(USER) == []


class TestHasLiveSession:
    def _check(self, session):
        with (
            patch.object(websocket_service.core_database, "SessionLocal") as session_local,
            patch.object(
                websocket_service.sessions_integration, "get_session_by_id_not_expired", return_value=session
            ) as lookup,
        ):
            result = websocket_service.has_live_session(USER, SESSION_1)
        session_local.return_value.__enter__.assert_called_once()
        lookup.assert_called_once_with(SESSION_1, session_local.return_value.__enter__.return_value)
        return result

    def test_an_unknown_or_expired_session_is_not_live(self):
        assert self._check(None) is False

    def test_a_live_session_of_the_user_is_live(self):
        assert self._check(SimpleNamespace(user_id=USER)) is True

    def test_a_session_of_another_user_is_not_live(self):
        assert self._check(SimpleNamespace(user_id=OTHER_USER)) is False


class TestDeliverHint:
    async def test_a_user_without_a_connection_gets_no_push(self):
        manager = websocket_manager.WebSocketManager()

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is False

    async def test_every_connection_of_the_user_receives_the_hint(self):
        first, second = AsyncMock(), AsyncMock()
        manager = await _manager_with(first, second)

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is True
        first.send_json.assert_awaited_once_with({"message": "hi"})
        second.send_json.assert_awaited_once_with({"message": "hi"})

    async def test_one_broken_connection_does_not_stop_the_others_and_is_dropped(self):
        broken, healthy = AsyncMock(), AsyncMock()
        broken.send_json.side_effect = RuntimeError("closed")
        manager = await _manager_with(broken, healthy)

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is True
        healthy.send_json.assert_awaited_once_with({"message": "hi"})
        assert manager.get_connections(USER) == [healthy]

    async def test_the_hint_fails_when_every_send_fails(self):
        broken = AsyncMock()
        broken.send_json.side_effect = RuntimeError("closed")
        manager = await _manager_with(broken)

        assert await websocket_service.deliver_hint(USER, {"message": "hi"}, manager) is False


class TestServeConnection:
    async def test_the_connection_is_registered_while_served_and_removed_after(self):
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()
        seen = []

        async def receive():
            seen.append(manager.get_connections(USER))
            raise WebSocketDisconnect()

        websocket.receive.side_effect = receive

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert seen == [[websocket]]
        assert manager.get_connections(USER) == []

    @pytest.mark.parametrize("frame", [{"text": "not json"}, {"bytes": b"\x00"}])
    async def test_a_data_frame_closes_the_connection(self, frame):
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()
        websocket.receive.side_effect = [{"type": "websocket.receive", **frame}]

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        websocket.close.assert_awaited_once_with(code=1008)
        assert manager.get_connections(USER) == []

    async def test_a_connection_is_closed_once_it_is_too_old(self, monkeypatch):
        monkeypatch.setattr(websocket_service, "MAX_CONNECTION_SECONDS", 0.01)
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()

        async def receive():
            await asyncio.sleep(1)

        websocket.receive.side_effect = receive

        await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        websocket.close.assert_awaited_once_with(code=1001)
        assert manager.get_connections(USER) == []

    async def test_the_connection_is_removed_however_the_loop_ends(self):
        manager = websocket_manager.WebSocketManager()
        websocket = AsyncMock()
        websocket.receive.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await websocket_service.serve_connection(websocket, USER, SESSION_1, manager)

        assert manager.get_connections(USER) == []
