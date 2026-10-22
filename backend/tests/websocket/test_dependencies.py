"""Tests for websocket.dependencies module."""

from jasil.backends.state_memory import MemoryState

import modules.websocket.dependencies as websocket_dependencies


def test_the_ticket_store_runs_over_the_given_state():
    state = MemoryState()

    ticket = websocket_dependencies.get_ws_ticket_store(state).create_ticket(7)

    assert websocket_dependencies.get_ws_ticket_store(state).consume_ticket(ticket) == 7
