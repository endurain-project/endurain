"""Tests for keyset (cursor) pagination.

Offset paging is not merely slower on a feed, it is wrong: a row inserted at the
head between two requests shifts every later row down one, so the client sees a
duplicate at the page boundary and never sees the row that was displaced. These
tests pin the properties that stop that.
"""

from datetime import UTC, datetime

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination


class TestCursorRoundTrip:
    def test_encodes_and_decodes_a_position(self):
        moment = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)

        assert core_pagination.decode_cursor(core_pagination.encode_cursor(moment, 42)) == (moment, 42)

    def test_cursor_is_opaque(self):
        """Clients must not be able to read or hand-craft positions."""
        cursor = core_pagination.encode_cursor(datetime(2026, 7, 29, tzinfo=UTC), 42)

        assert "2026" not in cursor
        assert "42" not in cursor

    def test_survives_a_separator_inside_the_timestamp(self):
        """rpartition, not partition: the id is the last field, not the second."""
        moment = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        raw = core_pagination.encode_cursor(moment, 7)

        assert core_pagination.decode_cursor(raw) == (moment, 7)

    @pytest.mark.parametrize(
        "bad",
        ["", "not-base64!!", "YWJj", "MjAyNi0wNy0yOXwxfDI="],
        ids=["empty", "not-base64", "no-separator", "unparseable-timestamp"],
    )
    def test_rejects_a_cursor_this_server_did_not_issue(self, bad):
        with pytest.raises(core_exceptions.InvalidInputError):
            core_pagination.decode_cursor(bad)


class TestCursorPage:
    def test_defaults_to_no_next_cursor(self):
        page = core_pagination.CursorPage[int](items=[1, 2], num_records=2)

        assert page.next_cursor is None

    def test_carries_no_total(self):
        """A COUNT per request is the cost keyset paging exists to avoid."""
        assert "total" not in core_pagination.CursorPage[int].model_fields
