"""Tests for websocket.router module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect, WebSocketException
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState

import modules.websocket.router as websocket_router
from modules.websocket.ticket_store import WsTicketStore


class TestIssueWsTicket:
    """Tests for the ticket endpoint."""

    @staticmethod
    def _client(store: WsTicketStore, user_id: int = 1) -> TestClient:
        import modules.auth.dependencies as auth_deps
        import modules.websocket.dependencies as websocket_dependencies

        app = FastAPI()
        app.include_router(websocket_router.router, prefix="/ws")
        app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
        app.dependency_overrides[websocket_dependencies.get_ws_ticket_store] = lambda: store
        return TestClient(app)

    def test_returns_ticket_dict(self):
        """The endpoint answers 201 with a 'ticket' key."""
        response = self._client(WsTicketStore(MemoryState())).post("/ws/ticket")
        assert response.status_code == 201
        assert isinstance(response.json()["ticket"], str)
        assert len(response.json()["ticket"]) > 0

    def test_ticket_is_consumable_for_correct_user(self):
        """The returned ticket is valid and bound to the authenticated user."""
        store = WsTicketStore(MemoryState())
        ticket = self._client(store, user_id=42).post("/ws/ticket").json()["ticket"]
        assert store.consume_ticket(ticket) == 42

    def test_different_calls_produce_unique_tickets(self):
        """Each call issues a unique ticket."""
        client = self._client(WsTicketStore(MemoryState()))
        assert client.post("/ws/ticket").json()["ticket"] != client.post("/ws/ticket").json()["ticket"]


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
        store = WsTicketStore(MemoryState())
        ticket = store.create_ticket(user_id=1)
        return store, ticket

    async def test_invalid_ticket_raises_policy_violation(self, mock_websocket, mock_manager):
        """websocket_endpoint raises WS_1008 for an unknown ticket."""
        store = WsTicketStore(MemoryState())
        with pytest.raises(WebSocketException) as exc_info:
            await websocket_router.websocket_endpoint(mock_websocket, "bad-ticket", store, mock_manager)
        assert exc_info.value.code == 1008
        mock_manager.connect.assert_not_awaited()

    @patch("modules.websocket.service.logger")
    async def test_websocket_endpoint_normal_operation(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint normal operation until disconnect."""
        user_id = 1
        store = WsTicketStore(MemoryState())
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
        mock_manager.disconnect.assert_called_once_with(user_id, mock_websocket)

        # No error logs for valid JSON
        mock_log.assert_not_called()

    @patch("modules.websocket.service.logger")
    async def test_websocket_endpoint_malformed_json(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint handling malformed JSON."""
        user_id = 1
        store = WsTicketStore(MemoryState())
        ticket = store.create_ticket(user_id=user_id)

        # Simulate malformed JSON (ValueError) then disconnect
        mock_websocket.receive_json.side_effect = [
            ValueError("Invalid JSON"),
            {"type": "valid"},
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)
        mock_log.warning.assert_called_once_with(
            "Received malformed JSON from a websocket client", extra={"user_id": user_id}
        )
        mock_manager.disconnect.assert_called_once_with(user_id, mock_websocket)

    @patch("modules.websocket.service.logger")
    async def test_websocket_endpoint_multiple_malformed_json(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint handling multiple malformed JSON messages."""
        user_id = 1
        store = WsTicketStore(MemoryState())
        ticket = store.create_ticket(user_id=user_id)

        mock_websocket.receive_json.side_effect = [
            ValueError("Invalid JSON 1"),
            ValueError("Invalid JSON 2"),
            {"type": "valid"},
            ValueError("Invalid JSON 3"),
            WebSocketDisconnect(),
        ]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        assert len(mock_log.method_calls) == 3
        mock_log.warning.assert_called_with(
            "Received malformed JSON from a websocket client", extra={"user_id": user_id}
        )

    @patch("modules.websocket.service.logger")
    async def test_websocket_endpoint_immediate_disconnect(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint with immediate disconnect."""
        user_id = 1
        store = WsTicketStore(MemoryState())
        ticket = store.create_ticket(user_id=user_id)

        mock_websocket.receive_json.side_effect = WebSocketDisconnect()

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        mock_manager.connect.assert_awaited_once_with(user_id, mock_websocket)
        mock_manager.disconnect.assert_called_once_with(user_id, mock_websocket)
        mock_log.assert_not_called()

    async def test_websocket_endpoint_different_users(self, mock_manager):
        """Test WebSocket endpoint with different user IDs."""
        store = WsTicketStore(MemoryState())
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
        mock_manager.disconnect.assert_any_call(1, ws1)
        mock_manager.disconnect.assert_any_call(2, ws2)
