"""Tests for websocket.router module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect, WebSocketException
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState
from jasil.testing import FixedClock

import modules.websocket.router as websocket_router
from core.attempt_state import StateUnavailableError
from modules.websocket.ticket_store import MAX_HANDSHAKES_PER_WINDOW, WsTicketOwner, WsTicketStore


class TestIssueWsTicket:
    """Tests for the ticket endpoint."""

    @staticmethod
    def _client(store: WsTicketStore, user_id: int = 1) -> TestClient:
        import modules.auth.dependencies as auth_deps
        import modules.websocket.dependencies as websocket_dependencies

        app = FastAPI()
        app.include_router(websocket_router.router, prefix="/ws")
        app.dependency_overrides[auth_deps.check_scopes] = lambda: None
        app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: user_id
        app.dependency_overrides[auth_deps.get_sid_from_access_token] = lambda: "session-1"
        app.dependency_overrides[websocket_dependencies.get_ws_ticket_store] = lambda: store
        return TestClient(app)

    def test_returns_ticket_dict(self):
        """The endpoint answers 201 with a 'ticket' key."""
        response = self._client(WsTicketStore(MemoryState(), FixedClock())).post("/ws/ticket")
        assert response.status_code == 201
        assert isinstance(response.json()["ticket"], str)
        assert len(response.json()["ticket"]) > 0

    def test_response_is_not_cacheable(self):
        """The ticket is a single-use credential, so no cache may keep it."""
        response = self._client(WsTicketStore(MemoryState(), FixedClock())).post("/ws/ticket")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"

    def test_ticket_is_consumable_for_correct_user(self):
        """The returned ticket is valid and bound to the authenticated user."""
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = self._client(store, user_id=42).post("/ws/ticket").json()["ticket"]
        assert store.consume_ticket(ticket) == WsTicketOwner(user_id=42, session_id="session-1")

    def test_different_calls_produce_unique_tickets(self):
        """Each call issues a unique ticket."""
        client = self._client(WsTicketStore(MemoryState(), FixedClock()))
        assert client.post("/ws/ticket").json()["ticket"] != client.post("/ws/ticket").json()["ticket"]


class TestWebSocketEndpoint:
    """Tests for websocket_endpoint function."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        websocket = AsyncMock()
        websocket.receive = AsyncMock()
        websocket.client = None
        return websocket

    @pytest.fixture(autouse=True)
    def live_session(self):
        """By default the ticket's session still exists."""
        with patch("modules.websocket.service.has_live_session", return_value=True) as check:
            yield check

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
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = store.create_ticket(user_id=1, session_id="s1")
        return store, ticket

    async def test_invalid_ticket_raises_policy_violation(self, mock_websocket, mock_manager):
        """websocket_endpoint raises WS_1008 for an unknown ticket."""
        store = WsTicketStore(MemoryState(), FixedClock())
        with pytest.raises(WebSocketException) as exc_info:
            await websocket_router.websocket_endpoint(mock_websocket, "bad-ticket", store, mock_manager)
        assert exc_info.value.code == 1008
        mock_manager.connect.assert_not_awaited()

    async def test_a_network_over_the_handshake_limit_is_refused_before_the_ticket_is_spent(
        self, mock_websocket, mock_manager
    ):
        """A handshake past the per-network limit closes with 1013 and leaves the ticket usable."""
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = store.create_ticket(user_id=1, session_id="s1")
        for _ in range(MAX_HANDSHAKES_PER_WINDOW):
            assert store.allow_handshake("unknown")

        with pytest.raises(WebSocketException) as exc_info:
            await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        assert exc_info.value.code == 1013
        mock_manager.connect.assert_not_awaited()
        assert store.consume_ticket(ticket) == WsTicketOwner(user_id=1, session_id="s1")

    async def test_a_ticket_whose_session_is_gone_is_closed_as_revoked(
        self, mock_websocket, mock_manager, live_session
    ):
        """A ticket issued before a revocation cannot open a socket the close event already missed."""
        live_session.return_value = False
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = store.create_ticket(user_id=4, session_id="gone")

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        live_session.assert_called_once_with(4, "gone")
        mock_websocket.accept.assert_awaited_once()
        mock_websocket.close.assert_awaited_once_with(code=4401)
        mock_manager.connect.assert_not_awaited()

    async def test_the_socket_is_bound_to_the_session_of_its_ticket(self, mock_websocket, mock_manager):
        """The manager registers the connection under the session the ticket was issued for."""
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = store.create_ticket(user_id=4, session_id="session-9")
        mock_websocket.receive.side_effect = [{"type": "websocket.disconnect", "code": 1001}]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        mock_manager.connect.assert_awaited_once_with(4, "session-9", mock_websocket)

    async def test_a_state_outage_closes_with_try_again_later(self, mock_websocket, mock_manager):
        """websocket_endpoint raises WS_1013 when the ticket store cannot be reached."""
        store = MagicMock()
        store.consume_ticket.side_effect = StateUnavailableError("down")
        with pytest.raises(WebSocketException) as exc_info:
            await websocket_router.websocket_endpoint(mock_websocket, "ticket", store, mock_manager)
        assert exc_info.value.code == 1013
        mock_manager.connect.assert_not_awaited()

    @patch("modules.websocket.service.logger")
    async def test_websocket_endpoint_normal_operation(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint normal operation until disconnect."""
        user_id = 1
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = store.create_ticket(user_id=user_id, session_id="s1")

        # Simulate the client leaving
        mock_websocket.receive.side_effect = [{"type": "websocket.disconnect", "code": 1001}]

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        # Verify connection was established with correct user_id
        mock_manager.connect.assert_awaited_once_with(user_id, "s1", mock_websocket)

        assert mock_websocket.receive.await_count == 1

        # Verify disconnect was called
        mock_manager.disconnect.assert_called_once_with(user_id, mock_websocket)

        # No error logs for valid JSON
        mock_log.assert_not_called()

    @patch("modules.websocket.service.logger")
    async def test_websocket_endpoint_immediate_disconnect(self, mock_log, mock_websocket, mock_manager):
        """Test WebSocket endpoint with immediate disconnect."""
        user_id = 1
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket = store.create_ticket(user_id=user_id, session_id="s1")

        mock_websocket.receive.side_effect = WebSocketDisconnect()

        await websocket_router.websocket_endpoint(mock_websocket, ticket, store, mock_manager)

        mock_manager.connect.assert_awaited_once_with(user_id, "s1", mock_websocket)
        mock_manager.disconnect.assert_called_once_with(user_id, mock_websocket)
        mock_log.assert_not_called()

    async def test_websocket_endpoint_different_users(self, mock_manager):
        """Test WebSocket endpoint with different user IDs."""
        store = WsTicketStore(MemoryState(), FixedClock())
        ticket1 = store.create_ticket(user_id=1, session_id="s1")
        ticket2 = store.create_ticket(user_id=2, session_id="s1")

        ws1 = AsyncMock()
        ws1.client = None
        ws1.receive = AsyncMock(side_effect=WebSocketDisconnect())

        ws2 = AsyncMock()
        ws2.client = None
        ws2.receive = AsyncMock(side_effect=WebSocketDisconnect())

        await websocket_router.websocket_endpoint(ws1, ticket1, store, mock_manager)
        await websocket_router.websocket_endpoint(ws2, ticket2, store, mock_manager)

        assert mock_manager.connect.await_count == 2
        mock_manager.connect.assert_any_await(1, "s1", ws1)
        mock_manager.connect.assert_any_await(2, "s1", ws2)
        assert mock_manager.disconnect.call_count == 2
        mock_manager.disconnect.assert_any_call(1, ws1)
        mock_manager.disconnect.assert_any_call(2, ws2)
