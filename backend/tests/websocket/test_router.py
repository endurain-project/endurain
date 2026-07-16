"""Tests for websocket.router module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect, WebSocketException

import modules.websocket.router as websocket_router
from modules.websocket.ticket_store import WsTicketStore


class TestIssueWsTicket:
    """Tests for issue_ws_ticket endpoint."""

    def test_returns_ticket_dict(self):
        """issue_ws_ticket returns a dict with a 'ticket' key."""
        store = WsTicketStore()
        result = websocket_router.issue_ws_ticket(user_id=1, ticket_store=store)
        assert isinstance(result, dict)
        assert "ticket" in result
        assert isinstance(result["ticket"], str)
        assert len(result["ticket"]) > 0

    def test_ticket_is_consumable_for_correct_user(self):
        """Returned ticket is valid and bound to the given user ID."""
        store = WsTicketStore()
        result = websocket_router.issue_ws_ticket(user_id=42, ticket_store=store)
        assert store.consume_ticket(result["ticket"]) == 42

    def test_different_calls_produce_unique_tickets(self):
        """Each call issues a unique ticket."""
        store = WsTicketStore()
        t1 = websocket_router.issue_ws_ticket(user_id=1, ticket_store=store)["ticket"]
        t2 = websocket_router.issue_ws_ticket(user_id=1, ticket_store=store)["ticket"]
        assert t1 != t2


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

    @pytest.fixture
    def ticket_store_with_user(self):
        """Return a WsTicketStore pre-loaded with a ticket for user 1."""
        store = WsTicketStore()
        ticket = store.create_ticket(user_id=1)
        return store, ticket

    async def test_invalid_ticket_raises_policy_violation(self, mock_websocket, mock_manager):
        """websocket_endpoint raises WS_1008 for an unknown ticket."""
        store = WsTicketStore()
        with pytest.raises(WebSocketException) as exc_info:
            await websocket_router.websocket_endpoint(mock_websocket, "bad-ticket", store, mock_manager)
        assert exc_info.value.code == 1008
        mock_manager.connect.assert_not_awaited()

    @patch("modules.websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_normal_operation(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint normal operation until disconnect."""
        user_id = 1
        store = WsTicketStore()
        ticket = store.create_ticket(user_id=user_id)

        # Simulate receiving messages then disconnect
        mock_websocket.receive_json.side_effect = [
            {"type": "ping"},
            {"type": "message"},
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        # Verify connection was established with correct user_id
        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)

        # Verify receive_json was called multiple times
        assert mock_websocket.receive_json.await_count == 3

        # Verify disconnect was called
        mock_manager.disconnect.assert_called_once_with(user_id)

        # No error logs for valid JSON
        mock_log.assert_not_called()

    @patch("modules.websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_malformed_json(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint handling malformed JSON."""
        user_id = 1
        store = WsTicketStore()
        ticket = store.create_ticket(user_id=user_id)

        # Simulate malformed JSON (ValueError) then disconnect
        mock_websocket.receive_json.side_effect = [
            ValueError("Invalid JSON"),
            {"type": "valid"},
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)
        mock_log.assert_called_once_with(f"Received malformed JSON from user {user_id}", "warning")
        mock_manager.disconnect.assert_called_once_with(user_id)

    @patch("modules.websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_multiple_malformed_json(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint handling multiple malformed JSON messages."""
        user_id = 1
        store = WsTicketStore()
        ticket = store.create_ticket(user_id=user_id)

        mock_websocket.receive_json.side_effect = [
            ValueError("Invalid JSON 1"),
            ValueError("Invalid JSON 2"),
            {"type": "valid"},
            ValueError("Invalid JSON 3"),
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        assert mock_log.call_count == 3
        mock_log.assert_called_with(f"Received malformed JSON from user {user_id}", "warning")

    @patch("modules.websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_immediate_disconnect(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint with immediate disconnect."""
        user_id = 1
        store = WsTicketStore()
        ticket = store.create_ticket(user_id=user_id)

        mock_websocket.receive_json.side_effect = WebSocketDisconnect()

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)
        mock_manager.disconnect.assert_called_once_with(user_id)
        mock_log.assert_not_called()

    @patch("modules.websocket.router.core_logger.print_to_log")
    async def test_websocket_endpoint_different_users(self, mock_log, mock_manager):
        """Test WebSocket endpoint with different user IDs."""
        store = WsTicketStore()
        ticket1 = store.create_ticket(user_id=1)
        ticket2 = store.create_ticket(user_id=2)

        ws1 = AsyncMock()
        ws1.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        ws2 = AsyncMock()
        ws2.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

        await websocket_router.websocket_endpoint(ws1, ticket1, store, mock_manager)
        await websocket_router.websocket_endpoint(ws2, ticket2, store, mock_manager)

        assert mock_manager.connect.await_count == 2
        mock_manager.connect.assert_any_await(1, ws1)
        mock_manager.connect.assert_any_await(2, ws2)
        assert mock_manager.disconnect.call_count == 2
        mock_manager.disconnect.assert_any_call(1)
        mock_manager.disconnect.assert_any_call(2)
