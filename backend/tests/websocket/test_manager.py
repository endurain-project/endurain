"""Tests for websocket.manager module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import websocket.manager as websocket_manager


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
        assert isinstance(manager.active_connections, dict)
        assert len(manager.active_connections) == 0

    @patch("websocket.manager.core_logger.print_to_log")
    async def test_connect(self, mock_log, manager, mock_websocket):
        """Test connecting a WebSocket."""
        user_id = 1

        await manager.connect(user_id, mock_websocket)

        # Verify websocket.accept was called
        mock_websocket.accept.assert_awaited_once()

        # Verify connection is stored
        assert user_id in manager.active_connections
        assert manager.active_connections[user_id] == mock_websocket

        # Verify logging
        mock_log.assert_called_once_with(
            f"WebSocket connected for user {user_id}", "debug"
        )

    @patch("websocket.manager.core_logger.print_to_log")
    async def test_connect_multiple_users(self, mock_log, manager):
        """Test connecting multiple WebSocket connections."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()

        await manager.connect(1, ws1)
        await manager.connect(2, ws2)

        assert len(manager.active_connections) == 2
        assert manager.active_connections[1] == ws1
        assert manager.active_connections[2] == ws2

    @patch("websocket.manager.core_logger.print_to_log")
    async def test_disconnect(self, mock_log, manager, mock_websocket):
        """Test disconnecting a WebSocket."""
        user_id = 1
        await manager.connect(user_id, mock_websocket)

        manager.disconnect(user_id)

        # Verify connection is removed
        assert user_id not in manager.active_connections

        # Verify logging
        assert mock_log.call_count == 2  # connect + disconnect
        mock_log.assert_any_call(f"WebSocket disconnected for user {user_id}", "debug")

    @patch("websocket.manager.core_logger.print_to_log")
    def test_disconnect_nonexistent_user(self, mock_log, manager):
        """Test disconnecting a non-existent user (no error)."""
        manager.disconnect(999)

        # Should not raise error, connection count remains 0
        assert len(manager.active_connections) == 0

        # Should only log if connection existed
        mock_log.assert_not_called()

    async def test_send_message(self, manager, mock_websocket):
        """Test sending a message to a specific user."""
        user_id = 1
        message = {"type": "notification", "data": "test"}

        await manager.connect(user_id, mock_websocket)
        await manager.send_message(user_id, message)

        # Verify send_json was called with correct message
        mock_websocket.send_json.assert_awaited_once_with(message)

    async def test_send_message_nonexistent_user(self, manager):
        """Test sending message to non-existent user (no error)."""
        message = {"type": "notification", "data": "test"}

        # Should not raise error
        await manager.send_message(999, message)

    async def test_broadcast(self, manager):
        """Test broadcasting a message to all connected users."""
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()

        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()

        ws3 = AsyncMock()
        ws3.accept = AsyncMock()
        ws3.send_json = AsyncMock()

        await manager.connect(1, ws1)
        await manager.connect(2, ws2)
        await manager.connect(3, ws3)

        message = {"type": "announcement", "data": "broadcast test"}
        await manager.broadcast(message)

        # Verify all connections received the message
        ws1.send_json.assert_awaited_once_with(message)
        ws2.send_json.assert_awaited_once_with(message)
        ws3.send_json.assert_awaited_once_with(message)

    async def test_broadcast_no_connections(self, manager):
        """Test broadcasting with no active connections (no error)."""
        message = {"type": "announcement", "data": "test"}

        # Should not raise error
        await manager.broadcast(message)

    async def test_get_connection(self, manager, mock_websocket):
        """Test retrieving a user's WebSocket connection."""
        user_id = 1
        await manager.connect(user_id, mock_websocket)

        connection = manager.get_connection(user_id)

        assert connection == mock_websocket

    def test_get_connection_nonexistent_user(self, manager):
        """Test retrieving connection for non-existent user returns None."""
        connection = manager.get_connection(999)

        assert connection is None

    async def test_replace_connection(self, manager):
        """Test replacing an existing connection (same user reconnects)."""
        old_ws = AsyncMock()
        old_ws.accept = AsyncMock()

        new_ws = AsyncMock()
        new_ws.accept = AsyncMock()

        user_id = 1

        # Connect with old websocket
        await manager.connect(user_id, old_ws)
        assert manager.active_connections[user_id] == old_ws

        # Reconnect with new websocket
        await manager.connect(user_id, new_ws)
        assert manager.active_connections[user_id] == new_ws

        # Old connection should be replaced
        assert len(manager.active_connections) == 1


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
