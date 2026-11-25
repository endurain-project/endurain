"""Tests that the XML activity file values read as the decoders store them, unusable values as ``None``."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

import modules.activities.activity_file_import.xml_values as xml_values


@pytest.mark.parametrize(("text", "expected"), [("12.5", 12.5), (" 3 ", 3.0), ("-4", -4.0)])
def test_a_finite_number_is_read(text, expected):
    assert xml_values.finite_number(text) == expected


@pytest.mark.parametrize("text", [None, "", "abc", "NaN", "nan", "inf", "-Infinity"])
def test_an_unusable_number_is_none(text):
    assert xml_values.finite_number(text) is None


def test_a_negative_value_is_none_and_a_whole_value_rounds():
    assert xml_values.non_negative(-0.1) is None
    assert xml_values.non_negative(0.0) == 0.0
    assert xml_values.whole(180.7) == 181
    assert xml_values.whole(-5.0) is None
    assert xml_values.whole(None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-06-20T08:00:00Z", datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)),
        ("2026-06-20T09:00:00+01:00", datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)),
        ("2026-06-20T08:00:00", datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)),
        ("2026-06-20T08:00:00.250Z", datetime(2026, 6, 20, 8, 0, 0, 250_000, tzinfo=UTC)),
        ("2026-06-20t08:00:00z", datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)),
    ],
)
def test_a_time_reads_as_utc_with_its_sub_second_part(text, expected):
    moment = xml_values.utc_time(text)

    assert moment == expected
    assert moment is not None and moment.utcoffset() == timedelta(0)


@pytest.mark.parametrize("text", [None, "", "2026-06-20", "yesterday", "2026-13-01T00:00:00Z"])
def test_a_missing_date_only_or_invalid_time_is_none(text):
    assert xml_values.utc_time(text) is None


def test_a_time_in_another_zone_keeps_its_instant():
    moment = xml_values.utc_time("2026-06-20T03:30:00-05:00")

    assert moment == datetime(2026, 6, 20, 3, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert moment is not None and moment.tzinfo == UTC


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        ("38.7", "-9.1", (38.7, -9.1)),
        ("90", "180", (90.0, 180.0)),
        ("0", "0", (0.0, 0.0)),
        ("91", "0", (None, None)),
        ("0", "-181", (None, None)),
        ("nan", "1", (None, None)),
        (None, "1", (None, None)),
    ],
)
def test_a_position_reads_both_coordinates_or_neither(lat, lon, expected):
    assert xml_values.position(lat, lon) == expected


def test_a_local_name_drops_the_namespace_and_keeps_the_case():
    assert xml_values.local_name("{http://www.topografix.com/GPX/1/1}trkpt") == "trkpt"
    assert xml_values.local_name("Trackpoint") == "Trackpoint"


def test_text_is_escaped_without_the_characters_xml_cannot_hold():
    assert xml_values.xml_text("a < b & c > d\x00\x1f\ttab\n") == "a &lt; b &amp; c &gt; d\ttab\n"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3, "3"),
        (100.0, "100.0"),
        (1e-05, "0.00001"),
        (41.16111877374351, "41.16111877374351"),
        (2.5e20, "250000000000000000000"),
    ],
)
def test_a_number_is_written_in_plain_decimal_notation(value, expected):
    assert xml_values.xml_number(value) == expected


@pytest.mark.parametrize("value", [0.1, 1 / 3, 83.5999984741211, -8.640724690631032, 1e-07, 6.02e23])
def test_a_written_float_reads_back_as_the_same_float(value):
    assert xml_values.finite_number(xml_values.xml_number(value)) == value


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC), "2026-06-20T08:00:00Z"),
        (datetime(2026, 6, 20, 8, 0, 0, 250_000, tzinfo=UTC), "2026-06-20T08:00:00.250Z"),
        (datetime(2026, 6, 20, 8, 0, 0, 123_456, tzinfo=UTC), "2026-06-20T08:00:00.123456Z"),
        (datetime(2026, 6, 20, 9, 0, 0, tzinfo=timezone(timedelta(hours=1))), "2026-06-20T08:00:00Z"),
    ],
)
def test_a_time_is_written_as_utc_and_reads_back_the_same(moment, expected):
    assert xml_values.xml_time(moment) == expected
    assert xml_values.utc_time(expected) == moment


def test_values_outside_the_extension_schema_ranges_are_none():
    assert [xml_values.xml_heart_rate(value) for value in (None, 0, 1, 255, 256)] == [None, None, 1, 255, None]
    assert [xml_values.xml_cadence(value) for value in (None, -1.0, 0.4, 89.6, 254.4, 254.6)] == [
        None,
        None,
        0,
        90,
        254,
        None,
    ]
    assert [xml_values.xml_unsigned_short(value) for value in (None, -1, 0, 65_535, 65_536)] == [
        None,
        None,
        0,
        65_535,
        None,
    ]
