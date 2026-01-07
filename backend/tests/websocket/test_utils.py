"""Tests for websocket.utils module."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import websocket.utils as websocket_utils


class TestNotifyFrontend:
    """Tests for notify_frontend function."""

    @pytest.fixture
    def mock_websocket_manager(self):
        """Create a mock WebSocketManager."""
        manager = MagicMock()
        manager.get_connection = MagicMock()
        return manager

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        websocket = AsyncMock()
        websocket.send_json = AsyncMock()
        return websocket

    async def test_notify_frontend_success(
        self, mock_websocket_manager, mock_websocket
    ):
        """Test successful notification delivery."""
        user_id = 1
        json_data = {"type": "notification", "message": "Test notification"}

        mock_websocket_manager.get_connection.return_value = mock_websocket

        result = await websocket_utils.notify_frontend(
            user_id, mock_websocket_manager, json_data
        )

        # Verify connection was retrieved
        mock_websocket_manager.get_connection.assert_called_once_with(user_id)

        # Verify message was sent
        mock_websocket.send_json.assert_awaited_once_with(json_data)

        # Verify return value
        assert result is True

    async def test_notify_frontend_no_connection_non_mfa(self, mock_websocket_manager):
        """Test notification when no connection exists (non-MFA message)."""
        user_id = 1
        json_data = {"type": "notification", "message": "Test notification"}

        mock_websocket_manager.get_connection.return_value = None

        result = await websocket_utils.notify_frontend(
            user_id, mock_websocket_manager, json_data
        )

        # Verify connection was attempted
        mock_websocket_manager.get_connection.assert_called_once_with(user_id)

        # Should return False when no connection
        assert result is False

    async def test_notify_frontend_no_connection_mfa_required(
        self, mock_websocket_manager
    ):
        """Test notification when no connection exists for MFA_REQUIRED message."""
        user_id = 1
        json_data = {"message": "MFA_REQUIRED", "type": "mfa"}

        mock_websocket_manager.get_connection.return_value = None

        # Should raise HTTPException for MFA_REQUIRED
        with pytest.raises(HTTPException) as exc_info:
            await websocket_utils.notify_frontend(
                user_id, mock_websocket_manager, json_data
            )

        # Verify exception details
        assert exc_info.value.status_code == 400
        assert f"No WebSocket connection for user {user_id}" in exc_info.value.detail

    async def test_notify_frontend_complex_json_data(
        self, mock_websocket_manager, mock_websocket
    ):
        """Test notification with complex JSON data."""
        user_id = 1
        json_data = {
            "type": "activity_update",
            "data": {
                "activity_id": 123,
                "status": "completed",
                "metrics": {"distance": 10.5, "duration": 3600},
            },
            "timestamp": "2026-01-07T10:00:00Z",
        }

        mock_websocket_manager.get_connection.return_value = mock_websocket

        result = await websocket_utils.notify_frontend(
            user_id, mock_websocket_manager, json_data
        )

        # Verify complex data was sent correctly
        mock_websocket.send_json.assert_awaited_once_with(json_data)
        assert result is True

    async def test_notify_frontend_multiple_users(
        self, mock_websocket_manager, mock_websocket
    ):
        """Test notifying multiple users sequentially."""
        json_data = {"type": "announcement", "message": "System update"}

        mock_websocket_manager.get_connection.return_value = mock_websocket

        # Notify multiple users
        result1 = await websocket_utils.notify_frontend(
            1, mock_websocket_manager, json_data
        )
        result2 = await websocket_utils.notify_frontend(
            2, mock_websocket_manager, json_data
        )
        result3 = await websocket_utils.notify_frontend(
            3, mock_websocket_manager, json_data
        )

        # All should succeed
        assert result1 is True
        assert result2 is True
        assert result3 is True

        # Verify all users were checked and notified
        assert mock_websocket_manager.get_connection.call_count == 3
        assert mock_websocket.send_json.await_count == 3

    async def test_notify_frontend_empty_json_data(
        self, mock_websocket_manager, mock_websocket
    ):
        """Test notification with empty JSON data."""
        user_id = 1
        json_data = {}

        mock_websocket_manager.get_connection.return_value = mock_websocket

        result = await websocket_utils.notify_frontend(
            user_id, mock_websocket_manager, json_data
        )

        # Should still send empty dict
        mock_websocket.send_json.assert_awaited_once_with({})
        assert result is True

    async def test_notify_frontend_mfa_required_case_sensitive(
        self, mock_websocket_manager
    ):
        """Test that MFA_REQUIRED check is case-sensitive."""
        user_id = 1

        # Different case - should not raise exception
        json_data1 = {"message": "mfa_required"}
        mock_websocket_manager.get_connection.return_value = None

        result = await websocket_utils.notify_frontend(
            user_id, mock_websocket_manager, json_data1
        )

        assert result is False  # No exception, just returns False

        # Exact match - should raise exception
        json_data2 = {"message": "MFA_REQUIRED"}

        with pytest.raises(HTTPException) as exc_info:
            await websocket_utils.notify_frontend(
                user_id, mock_websocket_manager, json_data2
            )

        assert exc_info.value.status_code == 400
