"""Tests that the recording contract keeps samples in time order, cuts sessions half-open and enforces file limits."""

from datetime import UTC, datetime, timedelta

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.recording as recording

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)


def _at(second: float) -> datetime:
    return _T0 + timedelta(seconds=second)


def _builder() -> recording.SamplesBuilder:
    return recording.SamplesBuilder(recording.FileLimits())


def test_rows_appended_in_order_keep_their_order_and_every_channel():
    builder = _builder()
    builder.append(_at(0), lat=1.0, lon=2.0, heart_rate=120)
    builder.append(_at(1), power=200, temperature=21.5)

    samples = builder.build()

    assert len(samples) == len(builder) == 2
    assert samples.time == (_at(0), _at(1))
    assert samples.lat == (1.0, None)
    assert samples.heart_rate == (120, None)
    assert samples.power == (None, 200)
    assert samples.temperature == (None, 21.5)


def test_rows_appended_out_of_order_are_sorted_keeping_the_order_of_equal_times():
    builder = _builder()
    builder.append(_at(2), heart_rate=3)
    builder.append(_at(0), heart_rate=1)
    builder.append(_at(1), heart_rate=2)
    builder.append(_at(1), heart_rate=22)

    samples = builder.build()

    assert samples.time == (_at(0), _at(1), _at(1), _at(2))
    assert samples.heart_rate == (1, 2, 22, 3)


def test_samples_between_is_half_open():
    builder = _builder()
    for second in range(5):
        builder.append(_at(second), heart_rate=second)
    samples = builder.build()

    first = recording.samples_between(samples, _at(0), _at(2))
    second = recording.samples_between(samples, _at(2), None)

    assert first.heart_rate == (0, 1)
    assert second.heart_rate == (2, 3, 4)
    assert len(recording.samples_between(samples, _at(10), None)) == 0


def test_the_sample_limit_refuses_the_file_past_it(monkeypatch):
    monkeypatch.setattr(recording, "MAX_SAMPLES_PER_FILE", 2)
    builder = _builder()
    builder.append(_at(0))
    builder.append(_at(1))

    with pytest.raises(core_exceptions.InvalidInputError, match="more than 2 samples"):
        builder.append(_at(2))


def test_the_session_limit_refuses_the_file_past_it(monkeypatch):
    monkeypatch.setattr(recording, "MAX_SESSIONS_PER_FILE", 1)
    limits = recording.FileLimits()
    limits.count_session()

    with pytest.raises(core_exceptions.InvalidInputError, match="more than 1 sessions"):
        limits.count_session()
