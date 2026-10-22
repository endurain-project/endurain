"""Tests for websocket.dependencies module."""

from types import SimpleNamespace

import pytest
from fastapi import WebSocketException
from jasil.backends.state_memory import MemoryState

import modules.websocket.dependencies as websocket_dependencies


def test_the_ticket_store_runs_over_the_given_state():
    state = MemoryState()

    ticket = websocket_dependencies.get_ws_ticket_store(state).create_ticket(7)

    assert websocket_dependencies.get_ws_ticket_store(state).consume_ticket(ticket) == 7


def _websocket(origin, allowed):
    headers = {} if origin is None else {"origin": origin}
    return SimpleNamespace(headers=headers, app=SimpleNamespace(state=SimpleNamespace(cors_allow_origins=allowed)))


@pytest.mark.parametrize("origin", [None, "https://endurain.example"])
def test_an_allowed_or_absent_origin_passes(origin):
    websocket_dependencies.require_allowed_origin(_websocket(origin, ["https://endurain.example"]))


def test_a_foreign_origin_is_refused():
    with pytest.raises(WebSocketException) as err:
        websocket_dependencies.require_allowed_origin(_websocket("https://evil.example", ["https://endurain.example"]))

    assert err.value.code == 1008


def test_every_browser_origin_is_refused_when_none_are_configured():
    websocket = _websocket("https://endurain.example", [])
    del websocket.app.state.cors_allow_origins

    with pytest.raises(WebSocketException):
        websocket_dependencies.require_allowed_origin(websocket)
