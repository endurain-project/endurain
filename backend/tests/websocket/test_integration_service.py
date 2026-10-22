"""Tests for websocket.integration_service module."""

import pytest
from jasil.testing import capture_hints, install_test_platform

import modules.websocket.integration_service as websocket_integration


@pytest.fixture
def hints(tmp_path):
    import jasil.testing as jasil_testing

    platform = install_test_platform(tmp_path)
    yield capture_hints(platform)
    jasil_testing.reset_all()


def test_a_push_is_published_for_the_user_key(hints):
    websocket_integration.push_to_user(7, {"message": "NEW", "notification_id": 3})

    assert hints == [("user:7", {"message": "NEW", "notification_id": 3})]


def test_a_push_the_channel_refuses_is_logged_not_raised(hints):
    websocket_integration.push_to_user(7, {"message": object()})

    assert hints == []


def test_an_oversized_push_is_dropped_not_raised(hints):
    websocket_integration.push_to_user(7, {"message": "x" * 10_000})

    assert hints == []
