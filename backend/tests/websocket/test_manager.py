"""Tests for websocket.manager module."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import modules.websocket.manager as websocket_manager
import modules.websocket.service as websocket_service


class TestWebSocketManager:
    """Tests for WebSocketManager class."""

    @pytest.fixture
    def manager(self):
        """Create a WebSocketManager instance."""
        return websocket_manager.WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        websocket = AsyncMock()
        websocket.accept = AsyncMock()
        websocket.send_json = AsyncMock()
        return websocket

    async def test_init(self, manager):
        """Test manager initialization."""
        assert manager.active_connections == {}

    @patch("modules.websocket.manager.logger")
    async def test_connect(self, mock_log, manager, mock_websocket):
        """Test connecting a WebSocket."""
        user_id = 1

        await manager.connect(user_id, mock_websocket)

        # Verify websocket.accept was called
        mock_websocket.accept.assert_awaited_once()

        # Verify connection is stored
        assert manager.active_connections[user_id] == [mock_websocket]

        # Verify logging
        mock_log.debug.assert_called_once_with("WebSocket connected", extra={"user_id": user_id})

    async def test_connect_multiple_users(self, manager):
        """Test connecting multiple WebSocket connections."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await manager.connect(1, ws1)
        await manager.connect(2, ws2)

        assert len(manager.active_connections) == 2
        assert manager.active_connections[1] == [ws1]
        assert manager.active_connections[2] == [ws2]

    @patch("modules.websocket.manager.logger")
    async def test_disconnect(self, mock_log, manager, mock_websocket):
        """Test disconnecting a WebSocket."""
        user_id = 1
        await manager.connect(user_id, mock_websocket)

        manager.disconnect(user_id, mock_websocket)

        # Verify connection is removed
        assert user_id not in manager.active_connections

        # Verify logging
        assert len(mock_log.method_calls) == 2  # connect + disconnect
        mock_log.debug.assert_any_call("WebSocket disconnected", extra={"user_id": user_id})

    @patch("modules.websocket.manager.logger")
    def test_disconnect_nonexistent_user(self, mock_log, manager):
        """Test disconnecting a non-existent user (no error)."""
        manager.disconnect(999, AsyncMock())

        # Should not raise error, connection count remains 0
        assert len(manager.active_connections) == 0

        # Should only log if connection existed
        mock_log.assert_not_called()

    async def test_get_connections(self, manager, mock_websocket):
        """Test retrieving a user's WebSocket connection."""
        user_id = 1
        await manager.connect(user_id, mock_websocket)

        assert manager.get_connections(user_id) == [mock_websocket]

    def test_get_connections_nonexistent_user(self, manager):
        """Test retrieving connections for a user with none returns an empty list."""
        assert manager.get_connections(999) == []

    async def test_a_second_connection_is_added_beside_the_first(self, manager):
        """Two tabs of one user are both registered."""
        first, second = AsyncMock(), AsyncMock()

        await manager.connect(1, first)
        await manager.connect(1, second)

        assert manager.get_connections(1) == [first, second]

    async def test_closing_one_tab_keeps_the_other_registered(self, manager):
        """Disconnecting by connection identity leaves the user's other tab receiving pushes."""
        first, second = AsyncMock(), AsyncMock()
        await manager.connect(1, first)
        await manager.connect(1, second)

        manager.disconnect(1, first)

        assert manager.get_connections(1) == [second]
        await websocket_service.deliver_hint(1, {"k": "v"}, manager)
        second.send_json.assert_awaited_once_with({"k": "v"})
        first.send_json.assert_not_awaited()

    async def test_the_last_disconnect_drops_the_user(self, manager):
        """A user with no connections left is not kept in the registry."""
        ws = AsyncMock()
        await manager.connect(1, ws)

        manager.disconnect(1, ws)
        manager.disconnect(1, ws)

        assert manager.active_connections == {}

    async def test_deliver_hint_reaches_every_connection(self, manager):
        """A message to a user goes to each of their tabs."""
        first, second = AsyncMock(), AsyncMock()
        await manager.connect(1, first)
        await manager.connect(1, second)

        await websocket_service.deliver_hint(1, {"k": "v"}, manager)

        first.send_json.assert_awaited_once_with({"k": "v"})
        second.send_json.assert_awaited_once_with({"k": "v"})


class TestGetWebSocketManager:
    """Tests for get_websocket_manager singleton function."""

    def test_get_websocket_manager_returns_instance(self):
        """Test that get_websocket_manager returns a WebSocketManager instance."""
        manager = websocket_manager.get_websocket_manager()

        assert isinstance(manager, websocket_manager.WebSocketManager)

    def test_get_websocket_manager_singleton(self):
        """Test that get_websocket_manager returns the same instance (singleton)."""
        # Clear the cache first
        websocket_manager.get_websocket_manager.cache_clear()

        manager1 = websocket_manager.get_websocket_manager()
        manager2 = websocket_manager.get_websocket_manager()

        assert manager1 is manager2

    def test_singleton_cache_clear(self):
        """Test that cache_clear creates a new instance."""
        manager1 = websocket_manager.get_websocket_manager()

        # Clear cache
        websocket_manager.get_websocket_manager.cache_clear()

        manager2 = websocket_manager.get_websocket_manager()

        # New instance created after cache clear
        assert manager1 is not manager2


class TestSendIsolation:
    """A failing connection must not stop the others from receiving."""

    @pytest.fixture
    def manager(self):
        return websocket_manager.WebSocketManager()

    async def test_deliver_hint_skips_a_broken_connection(self, manager):
        broken, healthy = AsyncMock(), AsyncMock()
        broken.send_json.side_effect = RuntimeError("closed")
        await manager.connect(1, broken)
        await manager.connect(1, healthy)

        await websocket_service.deliver_hint(1, {"k": "v"}, manager)

        healthy.send_json.assert_awaited_once_with({"k": "v"})

    async def test_a_stalled_connection_is_given_up_on(self, manager):
        async def never(_message):
            await asyncio.sleep(3600)

        stalled, healthy = AsyncMock(), AsyncMock()
        stalled.send_json.side_effect = never
        await manager.connect(1, stalled)
        await manager.connect(1, healthy)

        with patch.object(websocket_manager, "SEND_TIMEOUT_SECONDS", 0.01):
            failures = await websocket_manager.send_json_to_all(manager.get_connections(1), {"k": "v"})

        assert len(failures) == 1
        healthy.send_json.assert_awaited_once_with({"k": "v"})

    async def test_a_stalled_connection_is_unregistered_after_a_send(self, manager):
        async def never(_message):
            await asyncio.sleep(3600)

        stalled, healthy = AsyncMock(), AsyncMock()
        stalled.send_json.side_effect = never
        await manager.connect(1, stalled)
        await manager.connect(1, healthy)

        with patch.object(websocket_manager, "SEND_TIMEOUT_SECONDS", 0.01):
            await websocket_service.deliver_hint(1, {"k": "v"}, manager)

        assert manager.get_connections(1) == [healthy]

    async def test_an_unserializable_payload_keeps_the_connection(self, manager):
        socket = AsyncMock()
        socket.send_json.side_effect = TypeError("not serializable")
        await manager.connect(1, socket)

        await websocket_service.deliver_hint(1, {"k": object()}, manager)

        assert manager.get_connections(1) == [socket]
