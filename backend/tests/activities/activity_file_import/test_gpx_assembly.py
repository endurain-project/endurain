"""Tests for the activity a GPX file assembles to: decode the file, then assemble it."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from geopy.distance import geodesic

from tests.activities.activity_file_import import assembled

#: Longitude added to every equator point a test builds, so none sits at (0, 0), which cleaning drops as null island.
#: Distances along the equator do not depend on it.
_LON_ORIGIN = 1.0


def _write_gpx(tmp_path: Path, body: str) -> str:
    """Write GPX content to a temporary file.

    Args:
        tmp_path: Pytest temporary path fixture.
        body: GPX XML content.

    Returns:
        Path to the written file.
    """
    path = tmp_path / "activity.gpx"
    path.write_text(body.strip(), encoding="utf-8")
    return str(path)


def _gpx(tmp_path: Path, tracks: str, **kwargs):
    """Write a GPX document of tracks and assemble it.

    Args:
        tmp_path: Pytest temporary path fixture.
        tracks: The ``trk`` elements.
        **kwargs: The keyword arguments of ``assemble_gpx``.

    Returns:
        The payload.
    """
    xml = f'<gpx version="1.1" creator="pytest" xmlns:gpxtpx="http://example.com/gpxtpx">{tracks}</gpx>'
    return assembled.assemble_gpx(_write_gpx(tmp_path, xml), **kwargs)


def _points(rows: list[tuple[float, str, str]], lat: float = 0.0) -> str:
    """Build trackpoints.

    Args:
        rows: ``(longitude, time-of-day, inner XML)`` for each point.
        lat: The latitude of every point.

    Returns:
        The ``trkpt`` elements.
    """
    return "".join(
        f'<trkpt lat="{lat}" lon="{lon + _LON_ORIGIN}"><time>2025-01-01T{clock}Z</time>{inner}</trkpt>'
        for lon, clock, inner in rows
    )


def _six_km_track(tmp_path: Path, **kwargs):
    """Assemble a straight ~6 km east-west track of 100 m hops at the equator."""
    start = datetime(2025, 1, 1, tzinfo=UTC)
    points = "".join(
        f'<trkpt lat="0.0" lon="{_LON_ORIGIN + i * 0.0009:.4f}">'
        f"<time>{(start + timedelta(seconds=i * 30)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time></trkpt>"
        for i in range(61)
    )
    return _gpx(tmp_path, f"<trk><name>Run</name><type>Run</type><trkseg>{points}</trkseg></trk>", **kwargs)


def _on_off_watts(seconds: int) -> list[int]:
    """Return 1 Hz power alternating 30 s of 400 W and 30 s of 100 W."""
    return [400 if (second // 30) % 2 == 0 else 100 for second in range(seconds)]


def _coggan_np(watts: list[int]) -> float:
    """Return the normalized power of a 1 Hz list in plain Python: 30 s rolling mean, 4th-power mean, 4th root."""
    rolling = [sum(watts[i : i + 30]) / 30 for i in range(len(watts) - 29)]
    return (sum(w**4 for w in rolling) / len(rolling)) ** 0.25


def _powered_ride(tmp_path: Path, watts: list[int], **kwargs):
    """Assemble a ride east along the equator at about 10 m/s, one trackpoint a second carrying power."""
    start = datetime(2025, 1, 1, tzinfo=UTC)
    points = "".join(
        f'<trkpt lat="0.0" lon="{_LON_ORIGIN + i * 0.00009:.5f}">'
        f"<time>{(start + timedelta(seconds=i)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time>"
        f"<extensions><TrackPointExtension><power>{w}</power></TrackPointExtension></extensions></trkpt>"
        for i, w in enumerate(watts)
    )
    return _gpx(tmp_path, f"<trk><type>cycling</type><trkseg>{points}</trkseg></trk>", **kwargs)


class TestNormalizedPower:
    """GPX has no device normalized power, so the activity and its auto laps get Coggan's from the samples."""

    def test_activity_normalised_power_is_coggans(self, tmp_path):
        watts = _on_off_watts(600)

        result = _powered_ride(tmp_path, watts)

        assert result["activity"].normalized_power == round(_coggan_np(watts))

    def test_a_full_auto_lap_gets_coggans_from_the_samples_inside_it(self, tmp_path):
        watts = _on_off_watts(600)

        first = _powered_ride(tmp_path, watts)["laps"][0]

        # The lap is the first ~100 s; its window ends within a second of the lap's elapsed time.
        window = watts[: round(first["total_elapsed_time"])]
        assert first["normalized_power"] == pytest.approx(_coggan_np(window), abs=2)
        # The raw 4th-power mean of these samples is far higher.
        assert first["normalized_power"] < (sum(w**4 for w in window) / len(window)) ** 0.25 - 10


class TestAutoLapDistance:
    """GPX carries no device laps, so laps close at the caller's lap distance."""

    def test_metric_laps_close_every_km(self, tmp_path):
        result = _six_km_track(tmp_path)

        full = [lap for lap in result["laps"] if lap["total_distance"] >= 990]
        assert len(full) == 6

    def test_imperial_laps_close_every_mile(self, tmp_path):
        result = _six_km_track(tmp_path, lap_distance_km=1.609344)

        distances = [lap["total_distance"] for lap in result["laps"]]
        assert len(distances) == 4
        # A lap closes at the first sample past a multiple of a mile and keeps the whole 100 m step that closes it.
        assert all(1500 <= d < 1720 for d in distances[:3])
        assert distances[3] < 1609
        assert sum(distances) == pytest.approx(result["activity"].distance, abs=0.5)


class TestDistanceAndTime:
    """Distance, timer time and pace of a track, with its breaks and glitches."""

    def test_does_not_bridge_track_segments(self, tmp_path):
        body = (
            "<trk><name>Segmented run</name><type>Run</type>"
            + f"<trkseg>{_points([(0.0, '00:00:00', ''), (0.001, '00:00:10', '')])}</trkseg>"
            + f"<trkseg>{_points([(0.0, '00:20:20', ''), (0.001, '00:20:30', '')], lat=0.01)}</trkseg></trk>"
        )

        result = _gpx(tmp_path, body)

        expected = geodesic((0.0, 0.0), (0.0, 0.001)).meters + geodesic((0.01, 0.0), (0.01, 0.001)).meters
        assert result["activity"].distance == round(expected)
        # The first point of each segment has no previous point: a 0 placeholder.
        assert assembled.values(result, "speed")[0] == 0
        assert assembled.values(result, "speed")[2] == 0
        assert result["activity"].max_speed < 20
        assert all(lap["total_distance"] < 1000 for lap in result["laps"])

    def test_sums_distance_over_multiple_points_in_one_segment(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", ""), (0.002, "00:00:20", ""), (0.004, "00:00:40", "")]

        result = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")

        expected = (
            geodesic((0.0, 0.0), (0.0, 0.001)).meters
            + geodesic((0.0, 0.001), (0.0, 0.002)).meters
            + geodesic((0.0, 0.002), (0.0, 0.004)).meters
        )
        assert result["activity"].distance == round(expected)

    def test_excludes_pause_gap_from_timer_and_distance(self, tmp_path):
        """Issue #571: a 300 s recording pause inside one segment is not active time or distance."""
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", ""), (0.010, "00:05:10", ""), (0.011, "00:05:20", "")]

        result = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")

        expected = geodesic((0.0, 0.0), (0.0, 0.001)).meters + geodesic((0.0, 0.010), (0.0, 0.011)).meters
        activity = result["activity"]
        assert activity.distance == round(expected)
        assert activity.total_elapsed_time == 320
        assert activity.total_timer_time == 20
        assert activity.pace == pytest.approx(20 / expected, rel=0.01)
        assert assembled.values(result, "speed")[2] == 0
        assert all(lap["total_distance"] < 1000 for lap in result["laps"])

    def test_sparse_track_is_not_split_into_pauses(self, tmp_path):
        rows = [(0.001 * i, f"00:{(30 * i) // 60:02d}:{(30 * i) % 60:02d}", "") for i in range(5)]

        result = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")

        expected = 4 * geodesic((0.0, 0.0), (0.0, 0.001)).meters
        activity = result["activity"]
        assert activity.distance == round(expected)
        assert activity.total_timer_time == 120
        assert activity.pace == pytest.approx(120 / expected, rel=0.01)
        assert result["laps"]

    def test_timer_excludes_inter_segment_gap(self, tmp_path):
        body = (
            "<trk><type>Run</type>"
            + f"<trkseg>{_points([(0.0, '00:00:00', ''), (0.001, '00:00:10', '')])}</trkseg>"
            + f"<trkseg>{_points([(0.010, '00:10:10', ''), (0.011, '00:10:20', '')])}</trkseg></trk>"
        )

        activity = _gpx(tmp_path, body)["activity"]

        assert activity.total_elapsed_time == 620
        assert activity.total_timer_time == 20

    def test_gap_equal_to_threshold_counts_as_moving(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:15", ""), (0.002, "00:00:30", "")]

        activity = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")["activity"]

        expected = geodesic((0.0, 0.0), (0.0, 0.001)).meters + geodesic((0.0, 0.001), (0.0, 0.002)).meters
        assert activity.distance == round(expected)
        assert activity.total_timer_time == 30

    def test_all_paused_falls_back_to_elapsed_and_has_no_pace_or_speed(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:01:40", "")]

        activity = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")["activity"]

        assert activity.total_elapsed_time == 100
        assert activity.total_timer_time == 100
        assert activity.distance == 0
        # Zero distance gives no pace and no speeds (was 0).
        assert activity.pace is None
        assert activity.average_speed is None
        assert activity.max_speed is None

    def test_duplicate_timestamps_do_not_inflate_timer(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:00", ""), (0.002, "00:00:10", "")]

        activity = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")["activity"]

        assert activity.total_elapsed_time == 10
        assert activity.total_timer_time == 10

    def test_out_of_order_timestamp_does_not_inflate_timer(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", ""), (0.002, "00:00:05", ""), (0.003, "00:00:15", "")]

        activity = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")["activity"]

        assert activity.total_timer_time == 15

    def test_average_speed_is_distance_over_timer_time(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", ""), (0.003, "00:00:30", "")]

        result = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>")

        activity = result["activity"]
        expected = geodesic((0.0, 0.0), (0.0, 0.003)).meters / 30
        assert activity.average_speed == pytest.approx(expected, rel=0.01)

    def test_converts_offset_timestamps_to_utc(self, tmp_path):
        """Issue #588: timestamps with a non-UTC offset are stored as UTC."""
        trk = (
            '<trk><type>Run</type><trkseg><trkpt lat="0.0" lon="1.0"><time>2026-03-28T08:19:19-07:00</time></trkpt>'
            '<trkpt lat="0.0" lon="1.001"><time>2026-03-28T08:19:29-07:00</time></trkpt></trkseg></trk>'
        )

        result = _gpx(tmp_path, trk)

        assert result["activity"].start_time == datetime(2026, 3, 28, 15, 19, 19, tzinfo=UTC)
        assert result["activity"].end_time == datetime(2026, 3, 28, 15, 19, 29, tzinfo=UTC)
        assert result["samples"].offsets_ms == [0, 10_000]
        assert result["laps"][0]["start_time"] == "2026-03-28T15:19:19"


def _clock(seconds: int) -> str:
    """Return the time of day ``seconds`` after midnight."""
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class TestMovingTime:
    """Without a device timer the timer counts only the steps made at 0.5 m/s or more."""

    def test_standing_still_with_gps_jitter_before_a_walk_is_not_timed(self, tmp_path):
        jitter = [(0.000001 * (i % 2), _clock(i), "") for i in range(300)]
        step = 1.2 / 111_319.49
        walk = [(step * (i + 1), _clock(300 + i), "") for i in range(60)]

        activity = _gpx(tmp_path, f"<trk><type>Walk</type><trkseg>{_points(jitter + walk)}</trkseg></trk>")["activity"]

        assert activity.total_elapsed_time == 359
        assert activity.total_timer_time == pytest.approx(60.0, abs=1.0)

    def test_standing_still_with_phone_sized_gps_jitter_is_not_timed(self, tmp_path):
        # Fixes wandering 2.5 m either way every second: each step looks like 2.5 m/s, the place does not change.
        wobble = 2.5 / 111_319.49
        jitter = [(wobble * (i % 2), _clock(i), "") for i in range(300)]
        step = 1.2 / 111_319.49
        walk = [(step * (i + 1), _clock(300 + i), "") for i in range(60)]

        activity = _gpx(tmp_path, f"<trk><type>Walk</type><trkseg>{_points(jitter + walk)}</trkseg></trk>")["activity"]

        assert activity.total_timer_time == pytest.approx(60.0, abs=6.0)
        # Only the walk covers ground: 60 steps of 1.2 m, not the 300 jitter steps of 2.5 m as well.
        assert activity.distance == pytest.approx(72, abs=4)
        assert activity.average_speed == pytest.approx(1.2, rel=0.1)

    @pytest.mark.parametrize(("kind", "timed"), [("Swim", 120.0), ("Walk", 0.0)])
    def test_water_sports_move_from_a_slower_speed(self, tmp_path, kind, timed):
        # 0.4 m/s: a slow swimmer, but no walker.
        step = 0.4 / 111_319.49
        rows = [(step * i, _clock(i), "") for i in range(121)]

        activity = _gpx(tmp_path, f"<trk><type>{kind}</type><trkseg>{_points(rows)}</trkseg></trk>")["activity"]

        # A walk that never moves falls back to its elapsed time, so it is told by its distance instead.
        if timed:
            assert activity.total_timer_time == pytest.approx(timed, abs=1.0)
        assert activity.distance == pytest.approx(0.4 * timed, abs=2)

    def test_a_stop_with_samples_running_is_not_timed(self, tmp_path):
        step = 5.0 / 111_319.49
        rows = [(step * min(i, 100), _clock(i), "") for i in range(101)]
        rows += [(step * 100, _clock(i), "") for i in range(101, 221)]
        rows += [(step * (100 + i - 220), _clock(i), "") for i in range(221, 321)]

        activity = _gpx(tmp_path, f"<trk><type>Ride</type><trkseg>{_points(rows)}</trkseg></trk>")["activity"]

        assert activity.total_timer_time == pytest.approx(200.0, abs=1.0)
        assert activity.average_speed == pytest.approx(5.0, rel=0.02)


class TestTrackMetadata:
    """The name, type and description a GPX file gives."""

    def test_first_track_gives_name_type_and_description(self, tmp_path):
        first = _points([(0.0, "00:00:00", ""), (0.001, "00:00:10", "")])
        second = _points([(0.002, "00:00:20", ""), (0.003, "00:00:30", "")])
        body = (
            f"<trk><name>First</name><desc>One</desc><type>running</type><trkseg>{first}</trkseg></trk>"
            f"<trk><name>Second</name><desc>Two</desc><type>cycling</type><trkseg>{second}</trkseg></trk>"
        )

        result = _gpx(tmp_path, body)

        assert result["activity"].name == "First"
        assert result["activity"].description == "One"
        assert result["activity"].activity_type == "run"

    def test_road_biking_type_resolves_to_ride(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", "")]

        result = _gpx(tmp_path, f"<trk><type>road_biking</type><trkseg>{_points(rows)}</trkseg></trk>")

        assert result["activity"].activity_type == "ride"

    def test_reads_track_level_calories(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", "")]
        trk = (
            "<trk><name>Calories ride</name><extensions><gpxtrkx:TrackStatsExtension "
            'xmlns:gpxtrkx="http://example.com/gpxtrkx"><gpxtrkx:Calories>123.7</gpxtrkx:Calories>'
            f"</gpxtrkx:TrackStatsExtension></extensions><trkseg>{_points(rows)}</trkseg></trk>"
        )

        assert _gpx(tmp_path, trk)["activity"].calories == 123


class TestElevation:
    """Elevation streams and the gain and loss computed from them."""

    def test_sanitizes_elevation_values(self, tmp_path):
        rows = [
            (0.0, "00:00:00", "<ele>0</ele>"),
            (0.001, "00:00:10", "<ele>10000</ele>"),
            (0.002, "00:00:20", "<ele>-10000</ele>"),
            (0.003, "00:00:30", "<ele>12.5</ele>"),
        ]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        # Only the two plausible altitudes are samples' values, each at its own time.
        assert result["samples"].offsets_ms[0] == 0
        assert result["samples"].offsets_ms[-1] == 30_000
        assert [value is not None for value in result["samples"].elevation] == [True, False, False, True]

    def test_flat_track_stores_zero_elevation_gain(self, tmp_path):
        points = "".join(
            f'<trkpt lat="{40.0 + i * 0.001}" lon="-3.0"><ele>100.0</ele>'
            f"<time>2025-01-01T00:{(10 * i) // 60:02d}:{(10 * i) % 60:02d}Z</time></trkpt>"
            for i in range(15)
        )

        result = _gpx(tmp_path, f"<trk><name>Flat ride</name><trkseg>{points}</trkseg></trk>")

        assert result["activity"].elevation_gain == 0
        assert result["activity"].elevation_loss == 0
        assert result["laps"]
        assert all(lap["total_ascent"] == 0 for lap in result["laps"])
        assert all(lap["total_descent"] == 0 for lap in result["laps"])

    def test_invalid_elevation_stream_stores_none(self, tmp_path):
        rows = [(0.0, "00:00:00", "<ele>n/a</ele>"), (0.001, "00:01:00", "<ele>n/a</ele>")]

        result = _gpx(tmp_path, f"<trk><type>Ride</type><trkseg>{_points(rows)}</trkseg></trk>")

        assert not assembled.has(result, "elevation")
        assert result["activity"].elevation_gain is None
        assert result["activity"].elevation_loss is None


class TestSensorStreams:
    """Heart rate, cadence, power and temperature from the trackpoint extensions."""

    def test_without_extensions_creates_no_sensor_streams(self, tmp_path):
        rows = [(0.0, "00:00:00", ""), (0.001, "00:00:10", "")]

        result = _gpx(tmp_path, f"<trk><name>Sensor-free run</name><trkseg>{_points(rows)}</trkseg></trk>")

        assert not assembled.has(result, "heart_rate")
        assert assembled.values(result, "heart_rate") == []
        assert not assembled.has(result, "cadence")
        assert assembled.values(result, "cadence") == []
        assert not assembled.has(result, "power")
        assert not assembled.has(result, "temperature")
        assert result["activity"].average_hr is None
        assert result["activity"].max_hr is None

    def test_hr_only_extensions_omit_cadence_stream(self, tmp_path):
        rows = [
            (0.0, "00:00:00", "<extensions><TrackPointExtension><hr>140</hr></TrackPointExtension></extensions>"),
            (0.001, "00:00:10", "<extensions><TrackPointExtension><hr>150</hr></TrackPointExtension></extensions>"),
        ]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.has(result, "heart_rate")
        assert len(assembled.values(result, "heart_rate")) == 2
        # The last sample holds no time.
        assert result["activity"].average_hr == 140
        assert result["activity"].max_hr == 150
        assert not assembled.has(result, "cadence")
        assert assembled.values(result, "cadence") == []

    def test_does_not_zero_fill_missing_cadence_samples(self, tmp_path):
        rows = [
            (0.0, "00:00:00", "<extensions><TrackPointExtension><cad>80</cad></TrackPointExtension></extensions>"),
            (0.001, "00:00:10", ""),
            (0.002, "00:00:20", "<extensions><TrackPointExtension><cad>90</cad></TrackPointExtension></extensions>"),
        ]

        result = _gpx(tmp_path, f"<trk><name>Cadence gap ride</name><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.has(result, "cadence")
        assert assembled.values(result, "cadence") == [80, 90]
        # The 80 holds until the next kept sample, its 20 s capped at the 15 s pause threshold; 90 is last.
        assert result["activity"].average_cad == 80

    def test_doubles_running_cadence_to_spm(self, tmp_path):
        rows = [
            (0.0, "00:00:00", "<extensions><TrackPointExtension><cad>85</cad></TrackPointExtension></extensions>"),
            (0.001, "00:00:10", "<extensions><TrackPointExtension><cad>95</cad></TrackPointExtension></extensions>"),
        ]

        result = _gpx(
            tmp_path, f"<trk><name>Cadence run</name><type>running</type><trkseg>{_points(rows)}</trkseg></trk>"
        )

        assert result["activity"].activity_type == "run"
        assert assembled.values(result, "cadence") == [170, 190]
        assert result["activity"].average_cad == 170
        assert result["activity"].max_cad == 190

    def test_all_zero_hr_has_no_stream_and_no_average(self, tmp_path):
        rows = [
            (0.0, "00:00:00", "<extensions><TrackPointExtension><hr>0</hr></TrackPointExtension></extensions>"),
            (0.001, "00:00:10", "<extensions><TrackPointExtension><hr>0</hr></TrackPointExtension></extensions>"),
        ]

        result = _gpx(tmp_path, f"<trk><name>Dropout run</name><trkseg>{_points(rows)}</trkseg></trk>")

        # Zero is a dropout, so the stream has no heart rate at all.
        assert not assembled.has(result, "heart_rate")
        assert assembled.values(result, "heart_rate") == []
        assert result["activity"].average_hr is None
        assert result["activity"].max_hr is None

    def test_zero_hr_samples_are_dropouts_left_out_of_stream_average_and_maximum(self, tmp_path):
        ext = "<extensions><TrackPointExtension><hr>{}</hr></TrackPointExtension></extensions>"
        rows = [(0.001 * i, f"00:00:{10 * i:02d}", ext.format(hr)) for i, hr in enumerate((0, 140, 160, 160))]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.values(result, "heart_rate") == [140, 160, 160]
        assert result["activity"].average_hr == 150
        assert result["activity"].max_hr == 160

    def test_reads_namespaced_nested_values(self, tmp_path):
        ext = (
            "<extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>150</gpxtpx:hr><gpxtpx:cad>82</gpxtpx:cad>"
            '<ns3:wrapper xmlns:ns3="http://example.com/custom"><ns3:power>250</ns3:power></ns3:wrapper>'
            "</gpxtpx:TrackPointExtension></extensions>"
        )
        rows = [(0.0, "00:00:00", ext), (0.001, "00:00:10", ext)]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.values(result, "heart_rate") == [150, 150]
        assert assembled.values(result, "cadence") == [82, 82]
        assert assembled.values(result, "power") == [250, 250]

    def test_reads_unprefixed_values(self, tmp_path):
        ext = (
            "<extensions><TrackPointExtension><heartrate>145</heartrate><cad>77</cad><power>211</power>"
            "</TrackPointExtension></extensions>"
        )
        rows = [(0.0, "00:00:00", ext), (0.001, "00:00:10", ext)]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.values(result, "heart_rate")[0] == 145
        assert assembled.values(result, "cadence")[0] == 77
        assert assembled.values(result, "power")[0] == 211

    def test_reads_power_in_watts(self, tmp_path):
        ext = (
            "<extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>150</gpxtpx:hr>"
            "<gpxtpx:PowerInWatts>240</gpxtpx:PowerInWatts></gpxtpx:TrackPointExtension></extensions>"
        )
        rows = [(0.0, "00:00:00", ext), (0.001, "00:00:10", ext)]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.values(result, "heart_rate")[0] == 150
        assert not assembled.has(result, "cadence")
        assert assembled.values(result, "power") == [240, 240]

    def test_invalid_numbers_are_none_for_their_channel_only(self, tmp_path):
        ext = (
            "<extensions><TrackPointExtension><hr>not-a-number</hr><cad></cad><power>205.8</power>"
            "</TrackPointExtension></extensions>"
        )
        rows = [(0.0, "00:00:00", ext), (0.001, "00:00:10", ext)]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        # A bad value is missing for that channel (was 0); the others still read.
        assert not assembled.has(result, "heart_rate")
        assert not assembled.has(result, "cadence")
        assert assembled.values(result, "power") == [206, 206]

    def test_atemp_gives_a_temperature_stream(self, tmp_path):
        ext = "<extensions><TrackPointExtension><atemp>21.5</atemp></TrackPointExtension></extensions>"
        rows = [(0.0, "00:00:00", ext), (0.001, "00:00:10", ext)]

        result = _gpx(tmp_path, f"<trk><trkseg>{_points(rows)}</trkseg></trk>")

        assert assembled.has(result, "temperature")
        assert assembled.values(result, "temperature") == [21.5, 21.5]


def _steady_run(n_points: int, spikes: dict[int, float]) -> str:
    """Build a ~3 m/s eastbound run with 1 s spacing.

    Args:
        n_points: Number of trackpoints.
        spikes: Map of point index to extra longitude offset in degrees.

    Returns:
        The ``trk`` element.
    """
    step = 0.0000269  # ~3 m at the equator
    points = "".join(
        f'<trkpt lat="0.0" lon="{_LON_ORIGIN + i * step + spikes.get(i, 0.0):.7f}">'
        f"<time>2025-01-01T00:00:{i:02d}Z</time></trkpt>"
        for i in range(n_points)
    )
    return f"<trk><type>Run</type><trkseg>{points}</trkseg></trk>"


class TestMaxSpeed:
    """Max speed is robust against GPS glitches."""

    def test_single_gps_spike_does_not_set_max_speed(self, tmp_path):
        result = _gpx(tmp_path, _steady_run(30, {15: 0.00045}))  # one fix ~50 m ahead

        # The fix is dropped as a jump, so no speed between the neighbours' track shows it.
        assert max(assembled.values(result, "speed")) < 4
        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_two_adjacent_spiked_fixes_are_ignored(self, tmp_path):
        result = _gpx(tmp_path, _steady_run(30, {15: 0.00045, 16: 0.00045}))

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_sustained_fast_stretch_is_reported(self, tmp_path):
        step = 0.0000269
        lons = [_LON_ORIGIN + i * step for i in range(15)]
        for _ in range(4):  # 4 samples at ~9 m/s
            lons.append(lons[-1] + step * 3)
        for _ in range(15):
            lons.append(lons[-1] + step)
        points = "".join(
            f'<trkpt lat="0.0" lon="{lon:.7f}"><time>2025-01-01T00:00:{i:02d}Z</time></trkpt>'
            for i, lon in enumerate(lons)
        )

        result = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{points}</trkseg></trk>")

        # Four seconds at ~9 m/s and one at ~3 fill the best 5 s window: (4 x 9 + 3) / 5.
        assert result["activity"].max_speed == pytest.approx(7.8, abs=0.1)

    def test_fewer_than_window_samples_use_plain_max(self, tmp_path):
        result = _gpx(tmp_path, _steady_run(4, {2: 0.00006}))  # one fix ~6.7 m ahead, a ~10 m/s step

        assert result["activity"].max_speed == max(assembled.values(result, "speed"))
        assert result["activity"].max_speed > 9


def _segments(segments: list[list[tuple[float, str]]]) -> str:
    """Build a ``trk`` with one ``trkseg`` per entry.

    Args:
        segments: For each segment, ``(longitude, time-of-day)`` pairs on the equator.

    Returns:
        The ``trk`` element.
    """
    body = "".join(
        "<trkseg>"
        + "".join(
            f'<trkpt lat="0.0" lon="{_LON_ORIGIN + lon:.7f}"><time>2025-01-01T{clock}Z</time></trkpt>'
            for lon, clock in seg
        )
        + "</trkseg>"
        for seg in segments
    )
    return f"<trk><type>Run</type>{body}</trk>"


class TestMaxSpeedSegmentPlaceholders:
    """The 0 placeholder at each segment start is not a measured speed."""

    _STEP = 0.0000269  # ~3 m at the equator

    def _short_segments(self) -> str:
        """Five 2-point segments at ~3 m/s, each followed by a lone point (a pause)."""
        segments = []
        for i in range(5):
            segments.append([(i * 0.001, f"00:{2 * i:02d}:00"), (i * 0.001 + self._STEP, f"00:{2 * i:02d}:01")])
            segments.append([(i * 0.001 + 0.0005, f"00:{2 * i + 1:02d}:00")])
        return _segments(segments)

    def test_many_short_segments_report_the_measured_speed(self, tmp_path):
        result = _gpx(tmp_path, self._short_segments())

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_stored_speed_stream_keeps_the_placeholders_and_pace_has_none(self, tmp_path):
        result = _gpx(tmp_path, self._short_segments())

        vels = assembled.values(result, "speed")
        assert len(vels) == 15
        assert vels.count(0) == 10
        # Pace is derived from the speed, so it has a value only where the speed is above zero.
        assert len(assembled.pace(result)) == 5
        assert all(value == pytest.approx(1 / 3, rel=0.2) for value in assembled.pace(result))

    def test_average_speed_is_distance_over_timer_not_the_mean_of_samples(self, tmp_path):
        result = _gpx(tmp_path, self._short_segments())

        activity = result["activity"]
        assert activity.total_timer_time
        assert activity.average_speed == pytest.approx(activity.distance / activity.total_timer_time, rel=0.01)
        vels = assembled.values(result, "speed")
        assert activity.average_speed != pytest.approx(sum(vels) / len(vels))

    def test_a_lap_over_several_segments_reports_the_measured_speed(self, tmp_path):
        result = _gpx(tmp_path, self._short_segments())

        # The segments are one run of recording for the laps: 15 m of moving distance make one lap.
        (lap,) = result["laps"]
        assert lap["enhanced_max_speed"] == pytest.approx(3, abs=0.5)

    def test_non_advancing_clock_gives_no_measured_speed(self, tmp_path):
        result = _gpx(
            tmp_path,
            _segments(
                [
                    [(0.0, "00:00:00"), (self._STEP, "00:00:00"), (2 * self._STEP, "00:00:00")],
                    [(0.001, "00:01:00"), (0.001 + self._STEP, "00:01:00")],
                ]
            ),
        )

        assert result["activity"].max_speed is None

    def test_single_point_segments_do_not_raise(self, tmp_path):
        result = _gpx(
            tmp_path,
            _segments(
                [
                    [(0.0, "00:00:00")],
                    [(0.001, "00:01:00")],
                    [(0.002, "00:02:00"), (0.002 + self._STEP, "00:02:01")],
                ]
            ),
        )

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)

    def test_repeated_timestamps_leave_lap_and_max_speed_at_the_measured_speed(self, tmp_path):
        points = [(i * self._STEP, f"00:00:{i:02d}") for i in range(20) for _ in range(3)]

        result = _gpx(tmp_path, _segments([points]))

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)
        assert result["laps"][0]["enhanced_avg_speed"] == pytest.approx(3, abs=0.05)

    def test_a_dropped_gps_jump_leaves_the_step_across_it_its_full_time(self, tmp_path):
        # 3 m/s, with the fix at 10 s 100 m off (cleaning drops it) and a 12 m step from 9 s to 11 s across it.
        metre = 1 / 111_319.49

        def x(i: int) -> float:
            if i == 10:
                return 100 * metre
            return (3 * i + (6 if i > 10 else 0)) * metre

        points = [(x(i), f"00:00:{i:02d}") for i in range(20)]

        activity = _gpx(tmp_path, _segments([points]))["activity"]

        # The best 5 s holds three 3 m/s seconds and the 2 s at 6 m/s: 4.2 m/s.
        assert activity.max_speed == pytest.approx(4.2, rel=0.02)

    def test_a_position_that_updates_every_other_sub_second_sample_moves_at_its_true_speed(self, tmp_path):
        # Half-second samples whose position changes every other one: steps of 0 and 6 m/s, a 3 m/s rider.
        points = [(((k + 1) // 2) * self._STEP, f"00:00:{k / 2:04.1f}") for k in range(20)]

        activity = _gpx(tmp_path, _segments([points]))["activity"]

        assert activity.total_timer_time == pytest.approx(9.5, abs=1.0)
        # Not twice the speed, as when the 0 m/s steps were taken for standing still.
        assert activity.average_speed == pytest.approx(3.0, rel=0.1)
        assert activity.max_speed == pytest.approx(3.0, rel=0.05)

    def test_sub_second_samples_sharing_a_second_all_count(self, tmp_path):
        points = [(((k + 1) // 2) * self._STEP, f"00:00:{k / 2:04.1f}") for k in range(20)]

        result = _gpx(tmp_path, _segments([points]))

        assert result["activity"].max_speed == pytest.approx(3, abs=0.5)
        # The rider covers 3 m every second: 0 and 6 m/s over half-seconds. A lap averages its distance over its timer,
        # as the activity does, and the timer counts only the moving half-seconds.
        lap = result["laps"][0]
        assert lap["total_timer_time"] == pytest.approx(result["activity"].total_timer_time)
        assert lap["enhanced_avg_speed"] == pytest.approx(lap["total_distance"] / lap["total_timer_time"])
        assert lap["enhanced_avg_pace"] is not None


class TestTimeWeightedAutoLaps:
    """Auto laps average their sensor samples weighted by the time each holds."""

    def test_a_lap_averages_heart_rate_power_cadence_and_speed_by_time(self, tmp_path):
        ext = (
            "<extensions><TrackPointExtension><hr>{hr}</hr><cad>{cad}</cad></TrackPointExtension>"
            "<power>{power}</power></extensions>"
        )
        # 10 m hops; the first six samples are 1 s apart (fast), the next one is held 10 s (slow).
        clocks = [0, 1, 2, 3, 4, 5, 15, 16]
        rows = [
            (
                i * 0.00009,
                f"00:00:{clock:02d}",
                ext.format(
                    hr=100 if clock < 15 else 200, cad=60 if clock < 15 else 120, power=100 if clock < 15 else 300
                ),
            )
            for i, clock in enumerate(clocks)
        ]

        result = _gpx(tmp_path, f"<trk><type>Run</type><trkseg>{_points(rows)}</trkseg></trk>", lap_distance_km=10.0)

        (lap,) = result["laps"]
        # Samples at 0..5 s hold 1 s (100 each, the 5 s one holds 10 s); 15 s holds 1 s; 16 s is last.
        assert lap["avg_heart_rate"] == round((5 * 100 + 10 * 100 + 1 * 200) / 16)
        assert lap["avg_power"] == round((5 * 100 + 10 * 100 + 1 * 300) / 16)
        assert lap["avg_cadence"] == round((5 * 60 + 10 * 60 + 1 * 120) / 16 * 2)
        assert lap["max_heart_rate"] == 200
        # The lap's speed is its distance over its moving time: seven 10 m steps in 16 s.
        assert lap["total_timer_time"] == 16
        assert lap["enhanced_avg_speed"] == pytest.approx(lap["total_distance"] / 16)


#: A 22.5 m step east along the equator, in degrees of longitude.
_STEP_DEGREES = 0.000202
#: The seconds between samples of the laps tracks: 22.5 m in 5 s is 4.5 m/s.
_STEP_SECONDS = 5


def _lap_track(
    tmp_path: Path,
    *,
    steps: int = 156,
    sport: str = "Run",
    pause_at: int | None = None,
    stand_at: int | None = None,
    extra=None,
    step_degrees: float = _STEP_DEGREES,
    **kwargs,
):
    """Assemble a steady track east along the equator, optionally with a pause or a stand with GPS jitter.

    Args:
        tmp_path: Pytest temporary path fixture.
        steps: The number of steps; the track has one more sample.
        sport: The GPX activity type.
        pause_at: The step after which the athlete stops for 10 minutes at the same place.
        stand_at: The step after which the athlete stands 5 minutes, one jittering sample a second.
        extra: Callable from the sample index to the extension XML the sample carries.
        step_degrees: The longitude covered by one step.
        **kwargs: The keyword arguments of ``assemble_gpx``.

    Returns:
        The payload.
    """
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows: list[tuple[float, datetime, int]] = []
    clock = start
    for i in range(steps + 1):
        rows.append((i * step_degrees, clock, i))
        if pause_at == i:
            clock += timedelta(minutes=10)
            rows.append((i * step_degrees, clock, i))
        if stand_at == i:
            for second in range(1, 301):
                clock += timedelta(seconds=1)
                rows.append((i * step_degrees + (0.000014 if second % 2 else -0.000014), clock, i))
        clock += timedelta(seconds=_STEP_SECONDS)
    body = "".join(
        f'<trkpt lat="0.0" lon="{_LON_ORIGIN + lon:.6f}"><time>{moment.strftime("%Y-%m-%dT%H:%M:%SZ")}</time>'
        f"{extra(index) if extra else ''}</trkpt>"
        for lon, moment, index in rows
    )
    return _gpx(tmp_path, f"<trk><type>{sport}</type><trkseg>{body}</trkseg></trk>", **kwargs)


def _lap_km(result) -> list[float]:
    return [lap["total_distance"] / 1000 for lap in result["laps"]]


class TestAutoLapsOverTheWholeActivity:
    """Auto laps close at multiples of the lap distance over the moving distance, whatever the pauses."""

    def test_a_steady_run_gives_full_laps_and_the_remainder_which_sum_to_the_activity_distance(self, tmp_path):
        result = _lap_track(tmp_path)

        assert _lap_km(result) == pytest.approx([1.0, 1.0, 1.0, 0.5], abs=0.03)
        assert sum(lap["total_distance"] for lap in result["laps"]) == pytest.approx(
            result["activity"].distance, abs=0.5
        )

    def test_a_pause_inside_a_lap_changes_neither_the_laps_nor_their_distances(self, tmp_path):
        steady = _lap_track(tmp_path)
        paused = _lap_track(tmp_path, pause_at=70)

        assert len(paused["laps"]) == 4
        assert _lap_km(paused) == pytest.approx(_lap_km(steady), abs=1e-6)

    def test_the_lap_across_a_pause_counts_it_as_elapsed_time_but_not_as_timer_time(self, tmp_path):
        steady = _lap_track(tmp_path)["laps"][1]
        paused = _lap_track(tmp_path, pause_at=70)["laps"][1]

        assert paused["total_elapsed_time"] == steady["total_elapsed_time"] + 600
        assert paused["total_timer_time"] == steady["total_timer_time"]
        assert paused["enhanced_avg_speed"] == pytest.approx(paused["total_distance"] / paused["total_timer_time"])

    def test_standing_with_gps_jitter_adds_no_distance_and_no_lap(self, tmp_path):
        steady = _lap_track(tmp_path)
        standing = _lap_track(tmp_path, stand_at=70)

        assert len(standing["laps"]) == 4
        # Only the seconds around the stop, where the window still sees the walk, add a few metres of jitter.
        assert _lap_km(standing) == pytest.approx(_lap_km(steady), abs=0.06)
        assert standing["activity"].distance == pytest.approx(steady["activity"].distance, abs=60)

    def test_the_closing_sample_belongs_to_one_lap_only(self, tmp_path):
        # Lap 1 closes at the 45th step (45 x 22.5 m = 1012.5 m), whose sample carries a heart-rate spike.
        result = _lap_track(
            tmp_path,
            extra=lambda i: (
                f"<extensions><TrackPointExtension><hr>{200 if i == 45 else 100}</hr>"
                "</TrackPointExtension></extensions>"
            ),
        )

        first, second, *_ = result["laps"]
        assert first["max_heart_rate"] == 200
        assert second["max_heart_rate"] == 100
        assert second["avg_heart_rate"] == 100

    def test_the_laps_elevation_adds_up_to_the_activity_gain(self, tmp_path):
        result = _lap_track(tmp_path, extra=lambda i: f"<ele>{100 + 0.25 * i + (3 if i % 2 else 0)}</ele>")

        gain = result["activity"].elevation_gain
        assert gain
        assert abs(sum(lap["total_ascent"] for lap in result["laps"]) - gain) <= 2

    def test_the_laps_timers_add_up_to_the_activity_timer_across_a_pause(self, tmp_path):
        result = _lap_track(tmp_path, pause_at=70)

        assert sum(lap["total_timer_time"] for lap in result["laps"]) == pytest.approx(
            result["activity"].total_timer_time
        )
        assert sum(lap["total_elapsed_time"] for lap in result["laps"]) == result["activity"].total_elapsed_time

    def test_water_sports_move_from_0_3_metres_per_second_and_land_sports_from_0_5(self, tmp_path):
        slow = 0.4 * _STEP_SECONDS / 111_320

        swim = _lap_track(tmp_path, sport="swimming", step_degrees=slow, steps=300, lap_distance_km=0.2)
        walk = _lap_track(tmp_path, sport="Run", step_degrees=slow, steps=300, lap_distance_km=0.2)

        assert len(swim["laps"]) == 3
        assert walk["laps"] == []

    def test_a_flat_lap_has_zero_ascent_and_descent_and_no_elevation_leaves_them_none(self, tmp_path):
        flat = _lap_track(tmp_path, extra=lambda i: "<ele>100</ele>")
        without = _lap_track(tmp_path)

        assert all(lap["total_ascent"] == 0 and lap["total_descent"] == 0 for lap in flat["laps"])
        assert all(lap["total_ascent"] is None and lap["total_descent"] is None for lap in without["laps"])
