"""The activity file-parser registry parses real files, and what it parses is stored by the real ingestion path."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_file_import.integration_service as file_import_integration
import modules.activities.activity_file_import.parser_registry as registry
import modules.activities.activity_ingestion.enrichment_service as enrichment_service
import modules.activities.activity_laps.models as laps_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.models as streams_models
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
from tests._factories.users import make_user
from tests._helpers.auth import MOCK_USER_ID
from tests.activities.activity_file_import import fit_files

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)


def _stamp(seconds: int) -> str:
    return (_T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gpx(tmp_path: Path) -> str:
    points = "".join(
        f'<trkpt lat="{40.0 + 0.0009 * i:.4f}" lon="-3.0"><ele>{100 + i}</ele><time>{_stamp(10 * i)}</time>'
        "<extensions><gpxtpx:TrackPointExtension xmlns:gpxtpx="
        '"http://www.garmin.com/xmlschemas/TrackPointExtension/v1">'
        f"<gpxtpx:hr>{140 + i}</gpxtpx:hr></gpxtpx:TrackPointExtension></extensions></trkpt>"
        for i in range(31)
    )
    path = tmp_path / "ride.gpx"
    path.write_text(
        '<gpx version="1.1" creator="pytest" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>Lunch ride</name><type>Ride</type><trkseg>{points}</trkseg></trk></gpx>",
        encoding="utf-8",
    )
    return str(path)


def _tcx(tmp_path: Path) -> str:
    points = "".join(
        f"<Trackpoint><Time>{_stamp(10 * i)}</Time>"
        f"<Position><LatitudeDegrees>{40.0 + 0.0009 * i:.4f}</LatitudeDegrees>"
        "<LongitudeDegrees>-3.0</LongitudeDegrees></Position>"
        f"<AltitudeMeters>{100 + i}</AltitudeMeters><HeartRateBpm><Value>{140 + i}</Value></HeartRateBpm>"
        "</Trackpoint>"
        for i in range(31)
    )
    path = tmp_path / "run.tcx"
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        '<Activities><Activity Sport="Running"><Id>2026-06-20T08:00:00Z</Id>'
        '<Lap StartTime="2026-06-20T08:00:00Z"><TotalTimeSeconds>300</TotalTimeSeconds>'
        f"<DistanceMeters>1000</DistanceMeters><Track>{points}</Track></Lap>"
        "</Activity></Activities></TrainingCenterDatabase>",
        encoding="utf-8",
    )
    return str(path)


def _fit_session(start: datetime, *, latitude: float | None, seconds: int = 40) -> list[bytes]:
    """The records, lap and session of one activity starting at ``start``."""
    records = [
        fit_files.message(
            "record",
            timestamp=start + timedelta(seconds=10 * i),
            heart_rate=140 + i,
            enhanced_altitude=100 + i,
            **({"position_lat": latitude + 0.001 * i, "position_long": -3.0} if latitude is not None else {}),
        )
        for i in range(seconds // 10 + 1)
    ]
    end = start + timedelta(seconds=seconds)
    return [
        *records,
        fit_files.message(
            "lap",
            timestamp=end,
            start_time=start,
            total_elapsed_time=seconds,
            total_timer_time=seconds,
            total_distance=450,
        ),
        fit_files.message(
            "session",
            timestamp=end,
            start_time=start,
            total_elapsed_time=seconds,
            total_timer_time=seconds,
            total_distance=450,
            sport=1,
            avg_heart_rate=142,
            max_heart_rate=144,
        ),
    ]


def _fit(tmp_path: Path, *sessions: list[bytes]) -> str:
    path = tmp_path / "workout.fit"
    path.write_bytes(
        fit_files.fit_file(
            fit_files.message("file_id", type=4, manufacturer=255, time_created=_T0),
            *[message for session in sessions for message in session],
        )
    )
    return str(path)


def _channels(parsed_activity) -> set[str]:
    """The channels the parsed activity's samples carry."""
    samples = parsed_activity.components["samples"]
    if samples is None:
        return set()
    return {name for name in stream_constants.SAMPLE_CHANNELS if getattr(samples, name) is not None}


class TestRegistry:
    def test_every_supported_extension_has_a_parser(self):
        assert set(registry.supported_extensions()) == {".gpx", ".tcx", ".fit"}
        assert all(registry.get_parser(extension) is not None for extension in registry.supported_extensions())

    def test_the_extension_is_matched_without_regard_to_case(self):
        assert registry.get_parser(".GPX") is registry.get_parser(".gpx")

    def test_an_unsupported_extension_has_no_parser(self):
        assert registry.get_parser(".xyz") is None

    def test_the_public_surface_answers_like_the_registry(self):
        assert file_import_integration.supported_extensions() == registry.supported_extensions()
        assert file_import_integration.get_parser(".fit") is registry.get_parser(".fit")

    def test_an_automatic_lap_is_a_kilometre_or_a_mile_by_the_athletes_units(self):
        assert file_import_integration.auto_lap_distance_km(imperial=False) == 1.0
        assert file_import_integration.auto_lap_distance_km(imperial=True) == pytest.approx(1.609344)


class TestParsingFiles:
    def test_a_gpx_file_is_one_activity_with_its_streams_and_laps(self, tmp_path):
        parser = registry.get_parser(".gpx")

        parsed = parser(_gpx(tmp_path), MOCK_USER_ID, None, "UTC", 1.0)

        [activity] = parsed.activities
        assert activity.activity.name == "Lunch ride"
        assert activity.activity.user_id == MOCK_USER_ID
        assert 2500 < activity.activity.distance < 3500
        assert {"heart_rate", "elevation", "latitude", "longitude"} <= _channels(activity)
        assert len(activity.components["laps"]) >= 2

    def test_the_lap_distance_the_caller_gives_sets_the_gpx_laps(self, tmp_path):
        path = _gpx(tmp_path)
        parser = registry.get_parser(".gpx")

        per_km = parser(path, MOCK_USER_ID, None, "UTC", 1.0).activities[0].components["laps"]
        per_mile = parser(path, MOCK_USER_ID, None, "UTC", 1.609344).activities[0].components["laps"]

        assert len(per_km) > len(per_mile)

    def test_the_name_the_caller_gives_replaces_the_one_in_a_gpx_file(self, tmp_path):
        parsed = registry.get_parser(".gpx")(_gpx(tmp_path), MOCK_USER_ID, "My name", "UTC", 1.0)

        assert parsed.activities[0].activity.name == "My name"

    def test_the_name_the_caller_gives_names_a_tcx_activity(self, tmp_path):
        parsed = registry.get_parser(".tcx")(_tcx(tmp_path), MOCK_USER_ID, "My name", "UTC", 1.0)

        assert parsed.activities[0].activity.name == "My name"

    def test_a_fit_activity_without_a_given_name_takes_its_workout_name(self, tmp_path):
        path = _fit(tmp_path, [fit_files.message("workout", wkt_name="Intervals"), *_fit_session(_T0, latitude=40.0)])

        parsed = registry.get_parser(".fit")(path, MOCK_USER_ID, None, "UTC", 1.0)

        assert parsed.activities[0].activity.name == "Intervals"

    def test_the_name_the_caller_gives_replaces_a_fit_files_workout_name(self, tmp_path):
        path = _fit(tmp_path, [fit_files.message("workout", wkt_name="Intervals"), *_fit_session(_T0, latitude=40.0)])

        parsed = registry.get_parser(".fit")(path, MOCK_USER_ID, "My name", "UTC", 1.0)

        assert parsed.activities[0].activity.name == "My name"

    def test_the_name_the_caller_gives_names_a_fit_activity(self, tmp_path):
        path = _fit(tmp_path, _fit_session(_T0, latitude=40.0))

        parsed = registry.get_parser(".fit")(path, MOCK_USER_ID, "My name", "UTC", 1.0)

        assert parsed.activities[0].activity.name == "My name"

    def test_a_tcx_file_is_one_activity(self, tmp_path):
        parsed = registry.get_parser(".tcx")(_tcx(tmp_path), MOCK_USER_ID, None, "UTC", 1.0)

        [activity] = parsed.activities
        assert activity.activity.distance == 1000
        assert activity.activity.start_time == _T0
        assert "heart_rate" in _channels(activity)

    def test_a_fit_file_with_one_session_is_one_activity(self, tmp_path):
        parsed = registry.get_parser(".fit")(
            _fit(tmp_path, _fit_session(_T0, latitude=40.0)), MOCK_USER_ID, None, "UTC", 1.0
        )

        [activity] = parsed.activities
        assert activity.activity.distance == 450
        assert activity.activity.start_time == _T0
        assert activity.activity.average_hr == 142
        assert activity.activity.timezone == "Europe/Madrid"
        assert "latitude" in _channels(activity)
        assert len(activity.components["laps"]) == 1
        assert parsed.components == {"exercise_titles": []}

    def test_a_fit_file_with_two_sessions_is_two_activities_each_with_its_own_data(self, tmp_path):
        later = _T0 + timedelta(hours=1)
        path = _fit(
            tmp_path,
            _fit_session(_T0, latitude=40.0),
            _fit_session(later, latitude=None),
        )

        parsed = registry.get_parser(".fit")(path, MOCK_USER_ID, None, "Europe/Lisbon", 1.0)

        first, second = parsed.activities
        assert (first.activity.start_time, second.activity.start_time) == (_T0, later)
        assert "latitude" in _channels(first)
        assert "latitude" not in _channels(second)
        assert len(first.components["laps"]) == len(second.components["laps"]) == 1
        # The second session has no GPS and no offset, so it takes the athlete's timezone and not the first one's.
        assert first.activity.timezone == "Europe/Madrid"
        assert second.activity.timezone == "Europe/Lisbon"

    def test_a_multisport_fit_file_is_a_parent_over_its_legs(self, tmp_path):
        later = _T0 + timedelta(seconds=60)
        path = _fit(
            tmp_path,
            _fit_session(_T0, latitude=40.0),
            _fit_session(later, latitude=40.1),
            [fit_files.message("activity", timestamp=later + timedelta(seconds=40), type=1, num_sessions=2)],
        )

        parsed = registry.get_parser(".fit")(path, MOCK_USER_ID, None, "UTC", 1.0)

        assert parsed.parent is not None
        assert parsed.parent.activity.activity_type == activity_constants.ActivityType.MULTISPORT
        assert parsed.parent.activity.start_time == _T0
        assert parsed.parent.components["samples"] is None
        assert [leg.activity.start_time for leg in parsed.activities] == [_T0, later]

    def test_a_fit_file_with_two_sessions_but_no_multisport_type_has_no_parent(self, tmp_path):
        path = _fit(tmp_path, _fit_session(_T0, latitude=40.0), _fit_session(_T0 + timedelta(hours=1), latitude=None))

        assert registry.get_parser(".fit")(path, MOCK_USER_ID, None, "UTC", 1.0).parent is None

    def test_the_utc_offset_a_fit_file_reports_gives_the_timezone_when_it_has_no_gps(self, tmp_path):
        offset_message = fit_files.message(
            "activity", timestamp=_T0 + timedelta(seconds=40), local_timestamp=_T0 + timedelta(seconds=40 + 2 * 3600)
        )
        path = tmp_path / "indoor.fit"
        path.write_bytes(fit_files.fit_file(*_fit_session(_T0, latitude=None), offset_message))

        parsed = registry.get_parser(".fit")(str(path), MOCK_USER_ID, None, "Europe/Paris", 1.0)

        assert parsed.activities[0].activity.timezone == "Europe/Paris"


class TestStoringParsedFiles:
    @pytest.mark.parametrize("extension", [".gpx", ".tcx", ".fit"])
    def test_a_parsed_file_is_stored_with_its_samples_and_laps(self, db: Session, tmp_path, extension):
        user = make_user(db)
        builders = {".gpx": _gpx, ".tcx": _tcx, ".fit": lambda path: _fit(path, _fit_session(_T0, latitude=40.0))}
        parsed = registry.get_parser(extension)(builders[extension](tmp_path), user.id, None, "UTC", 1.0)

        privacy = users_privacy_settings_integration.get_privacy_settings(user.id, db)
        for activity in parsed.activities:
            enrichment_service.enrich_parsed_activity(
                activity.activity, user_id=user.id, user_privacy_settings=privacy, db=db
            )

        stored = [activity_integration.store_parsed_activity(activity, db) for activity in parsed.activities]

        [activity] = stored
        assert activity.user_id == user.id
        assert activity.start_time == parsed.activities[0].activity.start_time
        stored_samples = db.get(streams_models.ActivitySamples, activity.id)
        assert stored_samples is not None
        assert {
            name for name in stream_constants.SAMPLE_CHANNELS if getattr(stored_samples, name) is not None
        } == _channels(parsed.activities[0])
        assert not db.scalars(
            select(streams_models.ActivityStreams).where(streams_models.ActivityStreams.activity_id == activity.id)
        ).all()
        lap_count = len(
            db.scalars(
                select(laps_models.ActivityLaps).where(laps_models.ActivityLaps.activity_id == activity.id)
            ).all()
        )
        assert lap_count == len(parsed.activities[0].components["laps"]) > 0
