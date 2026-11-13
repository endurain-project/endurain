"""Tests for websocket.keys module."""

import uuid

import pytest

import modules.websocket.keys as websocket_keys

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")


def test_a_user_key_round_trips():
    assert websocket_keys.parse_user_key(websocket_keys.user_key(USER)) == USER


def test_a_control_key_round_trips():
    assert websocket_keys.parse_control_key(websocket_keys.control_key(USER)) == USER


@pytest.mark.parametrize(
    "key",
    [
        "",
        "42",
        "user:",
        "user:abc",
        "user:42",
        f"user:{USER}:8",
        f"device:{USER}",
        f"USER:{USER}",
        f"user: {USER}",
        f"user:{USER.hex}",
        "user:٣",
    ],
)
def test_a_key_that_does_not_address_a_user_is_ignored(key):
    assert websocket_keys.parse_user_key(key) is None


@pytest.mark.parametrize("key", ["", "control:", "control:abc", "control:7", f"user:{USER}"])
def test_a_key_that_is_not_a_control_key_is_ignored(key):
    assert websocket_keys.parse_control_key(key) is None
