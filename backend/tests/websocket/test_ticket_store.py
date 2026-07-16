"""Tests for websocket.ticket_store (provider-backed)."""

from unittest.mock import MagicMock, patch

import pytest

from infra.backends.state_memory import MemoryState
from infra.providers import StateBackendUnavailableError
from websocket.ticket_store import (
    TICKET_TTL_SECONDS,
    WsTicketStore,
    WsTicketStoreProtocol,
    WsTicketStoreUnavailableError,
    get_ws_ticket_store,
)


class TestWsTicketStoreProtocol:
    """Structural conformance to WsTicketStoreProtocol."""

    def test_store_satisfies_protocol(self):
        assert isinstance(WsTicketStore(state=MemoryState()), WsTicketStoreProtocol)


class TestWsTicketStore:
    """WsTicketStore backed by the platform StateProvider."""

    def _store(self) -> WsTicketStore:
        return WsTicketStore(state=MemoryState())

    def test_create_ticket_returns_string(self):
        ticket = self._store().create_ticket(user_id=1)
        assert isinstance(ticket, str)
        assert len(ticket) > 0

    def test_create_ticket_unique_per_call(self):
        store = self._store()
        assert store.create_ticket(1) != store.create_ticket(1)

    def test_consume_returns_user_id(self):
        store = self._store()
        ticket = store.create_ticket(user_id=42)
        assert store.consume_ticket(ticket) == 42

    def test_consume_is_single_use(self):
        store = self._store()
        ticket = store.create_ticket(user_id=7)
        assert store.consume_ticket(ticket) == 7
        assert store.consume_ticket(ticket) is None

    def test_consume_unknown_returns_none(self):
        assert self._store().consume_ticket("not-a-real-ticket") is None

    def test_consume_expired_returns_none(self):
        store = WsTicketStore(state=MemoryState())
        with patch("infra.backends.state_memory.time.monotonic") as clock:
            clock.return_value = 0.0
            ticket = store.create_ticket(user_id=3)
            clock.return_value = TICKET_TTL_SECONDS + 1
            assert store.consume_ticket(ticket) is None

    def test_ticket_ttl_is_30_seconds(self):
        assert TICKET_TTL_SECONDS == 30

    def test_create_ticket_retries_on_collision(self):
        state = MagicMock()
        state.set_if_absent.side_effect = [False, True]
        ticket = WsTicketStore(state=state).create_ticket(user_id=1)
        assert isinstance(ticket, str)
        assert state.set_if_absent.call_count == 2

    def test_consume_corrupt_value_returns_none_and_does_not_leak(self):
        state = MagicMock()
        state.get_and_delete.return_value = b"not-an-int"
        with patch("websocket.ticket_store.core_logger.print_to_log") as mock_log:
            assert WsTicketStore(state=state).consume_ticket("secret-ticket-abc") is None
        mock_log.assert_called_once()
        warning_msg = mock_log.call_args.args[0]
        assert "secret-ticket-abc" not in warning_msg
        assert "ws:ticket:" not in warning_msg


class TestWsTicketStoreUnavailable:
    """Backend outages surface as WsTicketStoreUnavailableError."""

    def test_create_ticket_raises(self):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")
        with pytest.raises(WsTicketStoreUnavailableError):
            WsTicketStore(state=state).create_ticket(user_id=1)

    def test_consume_ticket_raises(self):
        state = MagicMock()
        state.get_and_delete.side_effect = StateBackendUnavailableError("down")
        with pytest.raises(WsTicketStoreUnavailableError):
            WsTicketStore(state=state).consume_ticket("some-ticket")


class TestGetWsTicketStore:
    """get_ws_ticket_store: returns the module singleton."""

    def test_returns_singleton(self):
        assert get_ws_ticket_store() is get_ws_ticket_store()
        assert isinstance(get_ws_ticket_store(), WsTicketStoreProtocol)
