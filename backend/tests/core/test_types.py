"""Shared request-body types."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

import core.types as core_types

_INT32_MAX = 2**31 - 1


def test_int32_max_is_the_largest_value_of_an_integer_column():
    assert core_types.INT32_MAX == _INT32_MAX


class TestRecordId:
    """A body id must fit the integer column it references."""

    adapter = TypeAdapter(core_types.RecordId)

    @pytest.mark.parametrize("value", [1, _INT32_MAX])
    def test_an_id_inside_the_range_is_accepted(self, value):
        assert self.adapter.validate_python(value) == value

    @pytest.mark.parametrize("value", [0, -1, _INT32_MAX + 1, 2**63, "5", 1.0, True])
    def test_anything_else_is_rejected(self, value):
        with pytest.raises(ValidationError):
            self.adapter.validate_python(value)


class TestRecordDate:
    """A record date lies between 1900-01-01 and tomorrow in UTC, which any local today satisfies."""

    adapter = TypeAdapter(core_types.RecordDate)

    @staticmethod
    def _utc_today() -> date:
        return datetime.now(UTC).date()

    def test_the_lower_bound_is_accepted(self):
        assert self.adapter.validate_python(date(1900, 1, 1)) == date(1900, 1, 1)

    def test_a_date_before_1900_is_rejected(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python(date(1899, 12, 31))

    def test_today_and_tomorrow_are_accepted(self):
        today = self._utc_today()

        assert self.adapter.validate_python(today) == today
        assert self.adapter.validate_python(today + timedelta(days=1)) == today + timedelta(days=1)

    def test_two_days_ahead_is_rejected(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python(self._utc_today() + timedelta(days=2))

    def test_an_iso_string_is_parsed(self):
        assert self.adapter.validate_python("2000-02-03") == date(2000, 2, 3)


class TestRecordDateTime:
    """A record datetime follows the same bounds, compared in UTC when it carries an offset."""

    adapter = TypeAdapter(core_types.RecordDateTime)

    def test_now_is_accepted(self):
        now = datetime.now(UTC)

        assert self.adapter.validate_python(now) == now

    def test_a_naive_datetime_before_1900_is_rejected(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python(datetime(1899, 12, 31, 23, 59))

    def test_the_lower_bound_is_accepted(self):
        assert self.adapter.validate_python(datetime(1900, 1, 1)) == datetime(1900, 1, 1)

    def test_a_datetime_beyond_tomorrow_is_rejected(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python(datetime.now(UTC) + timedelta(days=2))

    def test_an_offset_is_compared_in_utc(self):
        just_before = datetime(1900, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1)))

        with pytest.raises(ValidationError):
            self.adapter.validate_python(just_before)
