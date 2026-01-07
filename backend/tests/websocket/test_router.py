"""Tests for websocket.router module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect

import websocket.router as websocket_router


class TestWebSocketEndpoint:
    """Tests for websocket_endpoint function."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        websocket = AsyncMock()
        websocket.receive_json = AsyncMock()
        return websocket

    @pytest.fixture
    def mock_manager(self):
        """Create a mock WebSocketManager."""
        manager = MagicMock()
        manager.connect = AsyncMock()
        manager.disconnect = MagicMock()
        return manager

    @patch("websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_normal_operation(
        self, mock_log, mock_websocket, mock_manager
    ):
        """Test WebSocket endpoint normal operation until disconnect."""
        user_id = 1

        # Simulate receiving messages then disconnect
        mock_websocket.receive_json.side_effect = [
            {"type": "ping"},
            {"type": "message"},
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, user_id, mock_manager)

        # Verify connection was established
        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)

        # Verify receive_json was called multiple times
        assert mock_websocket.receive_json.await_count == 3

        # Verify disconnect was called
        mock_manager.disconnect.assert_called_once_with(user_id)

        # No error logs for valid JSON
        mock_log.assert_not_called()

    @patch("websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_malformed_json(
        self, mock_log, mock_websocket, mock_manager
    ):
        """Test WebSocket endpoint handling malformed JSON."""
        user_id = 1

        # Simulate malformed JSON (ValueError) then disconnect
        mock_websocket.receive_json.side_effect = [
            ValueError("Invalid JSON"),
            {"type": "valid"},
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, user_id, mock_manager)

        # Verify connection was established
        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)

        # Verify warning was logged for malformed JSON
        mock_log.assert_called_once_with(
            f"Received malformed JSON from user {user_id}", "warning"
        )

        # Verify disconnect was called
        mock_manager.disconnect.assert_called_once_with(user_id)

    @patch("websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_multiple_malformed_json(
        self, mock_log, mock_websocket, mock_manager
    ):
        """Test WebSocket endpoint handling multiple malformed JSON messages."""
        user_id = 1

        # Simulate multiple malformed JSON messages
        mock_websocket.receive_json.side_effect = [
            ValueError("Invalid JSON 1"),
            ValueError("Invalid JSON 2"),
            {"type": "valid"},
            ValueError("Invalid JSON 3"),
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, user_id, mock_manager)

        # Verify warning was logged for each malformed JSON
        assert mock_log.call_count == 3
        mock_log.assert_called_with(
            f"Received malformed JSON from user {user_id}", "warning"
        )

    @patch("websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_immediate_disconnect(
        self, mock_log, mock_websocket, mock_manager
    ):
        """Test WebSocket endpoint with immediate disconnect."""
        user_id = 1

        # Simulate immediate disconnect
        mock_websocket.receive_json.side_effect = WebSocketDisconnect()

        await websocket_router.websocket_endpoint(mock_websocket, user_id, mock_manager)

        # Verify connection was established
        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)

        # Verify disconnect was called
        mock_manager.disconnect.assert_called_once_with(user_id)

        # No logs for normal disconnect
        mock_log.assert_not_called()

    @patch("websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_different_users(self, mock_log, mock_manager):
        """Test WebSocket endpoint with different user IDs."""
        ws1 = AsyncMock()
        ws1.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        ws2 = AsyncMock()
        ws2.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        # Test with different users
        await websocket_router.websocket_endpoint(ws1, 1, mock_manager)
        await websocket_router.websocket_endpoint(ws2, 2, mock_manager)

        # Verify both connections were established
        assert mock_manager.connect.await_count == 2
        mock_manager.connect.assert_any_await(1, ws1)
        mock_manager.connect.assert_any_await(2, ws2)

        # Verify both disconnects were called
        assert mock_manager.disconnect.call_count == 2
        mock_manager.disconnect.assert_any_call(1)
        mock_manager.disconnect.assert_any_call(2)

    @pytest.mark.skip(
        reason="Complex test requiring WebSocket protocol understanding - "
        "endpoint behavior verified through integration tests"
    )
    async def test_websocket_endpoint_send_receive_cycle(
        self, mock_websocket, mock_manager
    ):
        """
        Test bidirectional communication (complex WebSocket protocol).

        This test is skipped as it requires deep WebSocket protocol mocking.
        The endpoint is primarily receive-only in current implementation.
        """
        pass
