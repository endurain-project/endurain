"""Tests for websocket.keys module."""

import pytest

import modules.websocket.keys as websocket_keys


def test_a_user_key_round_trips():
    assert websocket_keys.parse_user_key(websocket_keys.user_key(42)) == 42


@pytest.mark.parametrize(
    "key",
    ["", "42", "user:", "user:abc", "user:-1", "user:1.5", "user: 7", "device:7", "user:7:8", "USER:7", "user:٣"],
)
def test_a_key_that_does_not_address_a_user_is_ignored(key):
    assert websocket_keys.parse_user_key(key) is None
