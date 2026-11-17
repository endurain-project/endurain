"""Tests for websocket.ticket_store (provider-backed)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from jasil.testing import FixedClock

import core.attempt_state as core_attempt_state
import core.hashing as core_hashing
from modules.websocket.ticket_store import (
    HANDSHAKE_WINDOW_SECONDS,
    MAX_HANDSHAKES_PER_WINDOW,
    TICKET_TTL_SECONDS,
    WsTicketOwner,
    WsTicketStore,
    _ticket_key,
)

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
SESSION_1 = uuid.UUID("5b0f6c1e-2d3a-4b7c-8e91-3a4d5c6b7e01")


class TestWsTicketStore:
    """WsTicketStore backed by the platform StateProvider."""

    def _store(self) -> WsTicketStore:
        return WsTicketStore(MemoryState(), FixedClock())

    def test_create_ticket_returns_string(self):
        ticket = self._store().create_ticket(user_id=USER, session_id=SESSION_1)
        assert isinstance(ticket, str)
        assert len(ticket) > 0

    def test_create_ticket_unique_per_call(self):
        store = self._store()
        assert store.create_ticket(USER, SESSION_1) != store.create_ticket(USER, SESSION_1)

    def test_consume_returns_user_id(self):
        store = self._store()
        ticket = store.create_ticket(user_id=USER, session_id=SESSION_1)
        assert store.consume_ticket(ticket) == WsTicketOwner(user_id=USER, session_id=SESSION_1)

    def test_consume_is_single_use(self):
        store = self._store()
        ticket = store.create_ticket(user_id=USER, session_id=SESSION_1)
        assert store.consume_ticket(ticket) == WsTicketOwner(user_id=USER, session_id=SESSION_1)
        assert store.consume_ticket(ticket) is None

    def test_consume_unknown_returns_none(self):
        assert self._store().consume_ticket("not-a-real-ticket") is None

    @pytest.mark.parametrize(
        "value",
        [
            b"7:s1",
            b"not-a-uuid:s1",
            f"{USER}:".encode(),
            f"{USER}:s1".encode(),
            str(USER).encode(),
        ],
    )
    def test_consume_a_malformed_value_returns_none(self, value):
        state = MemoryState()
        state.set_if_absent(_ticket_key("t"), value, ttl_seconds=TICKET_TTL_SECONDS)

        assert WsTicketStore(state, FixedClock()).consume_ticket("t") is None

    def test_consume_expired_returns_none(self):
        store = WsTicketStore(MemoryState(), FixedClock())
        with patch("jasil.backends.state_memory.time.monotonic") as clock:
            clock.return_value = 0.0
            ticket = store.create_ticket(user_id=USER, session_id=SESSION_1)
            clock.return_value = TICKET_TTL_SECONDS + 1
            assert store.consume_ticket(ticket) is None

    def test_state_key_holds_hash_not_raw_ticket(self):
        state = MemoryState()
        ticket = WsTicketStore(state, FixedClock()).create_ticket(user_id=USER, session_id=SESSION_1)
        keys = list(state.iter_keys("endurain:websocket:ticket"))
        assert len(keys) == 1
        assert ticket not in keys[0]
        assert keys[0] == core_attempt_state.key("websocket", "ticket", core_hashing.sha256_hex(ticket))

    def test_ticket_carries_the_session_of_the_requester(self):
        store = self._store()
        ticket = store.create_ticket(user_id=USER, session_id=SESSION_1)
        assert store.consume_ticket(ticket) == WsTicketOwner(user_id=USER, session_id=SESSION_1)

    def test_ticket_ttl_is_30_seconds(self):
        assert TICKET_TTL_SECONDS == 30

    def test_create_ticket_retries_on_collision(self):
        state = MagicMock()
        state.set_if_absent.side_effect = [False, True]
        ticket = WsTicketStore(state, FixedClock()).create_ticket(user_id=USER, session_id=SESSION_1)
        assert isinstance(ticket, str)
        assert state.set_if_absent.call_count == 2

    def test_consume_corrupt_value_returns_none_and_does_not_leak(self):
        state = MagicMock()
        state.get_and_delete.return_value = b"not-an-int"
        with patch("modules.websocket.ticket_store.logger") as mock_log:
            assert WsTicketStore(state, FixedClock()).consume_ticket("secret-ticket-abc") is None
        assert len(mock_log.method_calls) == 1
        warning_msg = mock_log.warning.call_args.args[0]
        assert "secret-ticket-abc" not in warning_msg
        assert "endurain:websocket:ticket" not in warning_msg


class TestHandshakeLimit:
    """The per-network handshake counter in the platform state."""

    def test_a_network_is_allowed_up_to_the_limit_and_refused_past_it(self):
        store = WsTicketStore(MemoryState(), FixedClock())
        assert all(store.allow_handshake("203.0.113.5") for _ in range(MAX_HANDSHAKES_PER_WINDOW))
        assert not store.allow_handshake("203.0.113.5")

    def test_networks_are_counted_apart(self):
        store = WsTicketStore(MemoryState(), FixedClock())
        for _ in range(MAX_HANDSHAKES_PER_WINDOW + 1):
            store.allow_handshake("203.0.113.5")
        assert store.allow_handshake("203.0.113.6")

    def test_the_next_window_starts_fresh_even_if_attempts_never_paused(self):
        clock = FixedClock()
        store = WsTicketStore(MemoryState(), clock)
        for _ in range(MAX_HANDSHAKES_PER_WINDOW + 1):
            store.allow_handshake("203.0.113.5")
        assert not store.allow_handshake("203.0.113.5")

        clock.advance(HANDSHAKE_WINDOW_SECONDS)

        assert store.allow_handshake("203.0.113.5")

    def test_attempts_do_not_extend_the_window(self):
        clock = FixedClock()
        state = MemoryState()
        store = WsTicketStore(state, clock)
        for _ in range(MAX_HANDSHAKES_PER_WINDOW + 1):
            clock.advance(HANDSHAKE_WINDOW_SECONDS / (MAX_HANDSHAKES_PER_WINDOW + 5))
            store.allow_handshake("203.0.113.5")
        clock.advance(HANDSHAKE_WINDOW_SECONDS)
        assert store.allow_handshake("203.0.113.5")

    def test_a_counter_always_expires(self):
        state = MagicMock()
        state.incr.return_value = 1
        WsTicketStore(state, FixedClock()).allow_handshake("203.0.113.5")
        assert state.incr.call_args.kwargs["ttl_seconds"] == 2 * HANDSHAKE_WINDOW_SECONDS

    def test_the_count_lives_in_the_shared_state(self):
        state = MemoryState()
        for _ in range(MAX_HANDSHAKES_PER_WINDOW):
            WsTicketStore(state, FixedClock()).allow_handshake("203.0.113.5")
        assert not WsTicketStore(state, FixedClock()).allow_handshake("203.0.113.5")

    def test_a_state_outage_surfaces_as_unavailable(self):
        state = MagicMock()
        state.incr.side_effect = StateBackendUnavailableError("down")
        with pytest.raises(core_attempt_state.StateUnavailableError):
            WsTicketStore(state, FixedClock()).allow_handshake("203.0.113.5")


class TestWsTicketStoreUnavailable:
    """Backend outages surface as core_attempt_state.StateUnavailableError."""

    def test_create_ticket_raises(self):
        state = MagicMock()
        state.set_if_absent.side_effect = StateBackendUnavailableError("down")
        with pytest.raises(core_attempt_state.StateUnavailableError):
            WsTicketStore(state, FixedClock()).create_ticket(user_id=USER, session_id=SESSION_1)

    def test_consume_ticket_raises(self):
        state = MagicMock()
        state.get_and_delete.side_effect = StateBackendUnavailableError("down")
        with pytest.raises(core_attempt_state.StateUnavailableError):
            WsTicketStore(state, FixedClock()).consume_ticket("some-ticket")
