"""Tests for the string enums that map to a stored integer."""

import pytest
from pydantic import BaseModel, ValidationError

from core.stored_enum import StoredStrEnum, to_stored


class Level(StoredStrEnum):
    """A two-member enum for the tests."""

    LOW = ("low", 0, "Low level")
    HIGH = ("high", 5)


class Request(BaseModel):
    """A request body: only the string is accepted."""

    level: Level


def test_member_carries_value_stored_integer_and_label():
    assert Level.LOW == "low"
    assert Level.LOW.stored == 0
    assert Level.LOW.label == "Low level"
    assert Level.HIGH.label == "high"


def test_from_stored_returns_the_member():
    assert Level.from_stored(5) is Level.HIGH


def test_from_stored_refuses_an_unknown_integer():
    with pytest.raises(ValueError, match="not a stored value"):
        Level.from_stored(3)


def test_accept_stored_maps_integers_and_passes_other_values():
    assert Level.accept_stored(0) is Level.LOW
    assert Level.accept_stored("high") == "high"
    assert Level.accept_stored(True) is True


def test_a_request_refuses_the_stored_integer():
    assert Request(level="high").level is Level.HIGH
    with pytest.raises(ValidationError):
        Request(level=5)


def test_to_stored_replaces_members_in_nested_mappings_and_lists_and_keeps_other_values():
    values = {
        "level": Level.HIGH,
        "plain": "high",
        "nested": {"inner": Level.LOW, "count": 3},
        "listed": [Level.HIGH, "low", {"deep": Level.LOW}],
    }

    assert to_stored(values) == {
        "level": 5,
        "plain": "high",
        "nested": {"inner": 0, "count": 3},
        "listed": [5, "low", {"deep": 0}],
    }
