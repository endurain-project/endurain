"""Garmin FIT file parsing.

Pure: file bytes in, parsed activity data out, with no database, provider or
crud coupling, so a parser is unit-testable with a file alone.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

import fitdecode

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_file_import.fit_frames as activity_file_import_fit_frames
import modules.activities.activity_file_import.parser_utils as activity_file_import_parser_utils
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.computation as activities_computation

logger = core_logger.get_logger(__name__)


class FitSession(TypedDict):
    """A FIT session's summary, as the activity is built from it.

    Attributes:
        initial_latitude: Start latitude in degrees; the first GPS waypoint's when the session has none.
        initial_longitude: Start longitude in degrees; the first GPS waypoint's when the session has none.
        city: City of the activity; resolved after parsing.
        town: Town of the activity; resolved after parsing.
        country: Country of the activity; resolved after parsing.
        activity_type: The FIT sport, or the sub-sport that names the activity better.
        first_waypoint_time: When the session started.
        last_waypoint_time: Start plus the elapsed time.
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timer seconds.
        calories: Calories.
        distance: Distance in meters.
        avg_hr: Average heart rate in bpm.
        max_hr: Maximum heart rate in bpm.
        avg_cadence: Average cadence.
        max_cadence: Maximum cadence.
        avg_power: Average power in watts.
        max_power: Maximum power in watts.
        ele_gain: Ascent in meters.
        ele_loss: Descent in meters.
        np: Normalized power in watts.
        avg_speed: Average speed in m/s.
        max_speed: Maximum speed in m/s.
        workout_feeling: Workout feel, 0-100.
        workout_rpe: Workout RPE, 10-100.
        total_cycles: Cycles (strokes, strides).
    """

    initial_latitude: float | None
    initial_longitude: float | None
    city: str | None
    town: str | None
    country: str | None
    activity_type: activity_file_import_fit_frames.FitEnum
    first_waypoint_time: datetime
    last_waypoint_time: datetime
    total_elapsed_time: float
    total_timer_time: float
    calories: int | None
    distance: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_cadence: int | None
    max_cadence: int | None
    avg_fractional_cadence: float | None
    max_fractional_cadence: float | None
    avg_power: int | None
    max_power: int | None
    ele_gain: int | None
    ele_loss: int | None
    np: int | None
    avg_speed: float | None
    max_speed: float | None
    workout_feeling: int | None
    workout_rpe: int | None
    total_cycles: int | None


class FitSplit(TypedDict):
    """A FIT split message's fields, the positions in semicircles as decoded."""

    split_type: activity_file_import_fit_frames.FitEnum | None
    total_elapsed_time: float | None
    total_timer_time: float | None
    total_distance: float | None
    avg_speed: float | None
    start_time: datetime | None
    total_ascent: int | None
    total_descent: int | None
    start_position_lat: int | None
    start_position_long: int | None
    end_position_lat: int | None
    end_position_long: int | None
    max_speed: float | None
    end_time: datetime | None
    total_calories: int | None
    start_elevation: float | None


class FitParsePayload(TypedDict):
    """Everything the first FIT stage read from a file, before it is split into activities.

    Attributes:
        sessions: The session summaries, one per activity.
        time_offset: The signed ``device_settings`` UTC offset in seconds.
        activity_time_offset: The ``activity`` message's UTC offset in seconds, when it carries one.
        activity_name: The workout name, or the override.
        laps: Every lap of the file.
        splits: Every split of the file.
        split_summary: Every split summary of the file.
        sets: Every workout set, as raw rows.
        workout_steps: Every planned workout step.
        lengths: Every pool length.
        file_id: The file's identification.
        intraday_steps: Monitoring step samples.
        intraday_heart_rate: Monitoring heart-rate samples.
        resting_heart_rate: The monitoring resting heart rate, when the file has one.
        exercise_titles: The file's exercise titles.
    """

    sessions: list[FitSession]
    time_offset: int | None
    activity_time_offset: int | None
    activity_name: str
    is_elevation_set: bool
    ele_waypoints: list[activity_streams_contracts.ElevationWaypoint]
    is_power_set: bool
    power_waypoints: list[activity_streams_contracts.PowerWaypoint]
    is_heart_rate_set: bool
    hr_waypoints: list[activity_streams_contracts.HeartRateWaypoint]
    is_velocity_set: bool
    vel_waypoints: list[activity_streams_contracts.VelocityWaypoint]
    pace_waypoints: list[activity_streams_contracts.PaceWaypoint]
    is_temperature_set: bool
    temp_waypoints: list[activity_streams_contracts.TemperatureWaypoint]
    is_cadence_set: bool
    cad_waypoints: list[activity_streams_contracts.CadenceWaypoint]
    is_lat_lon_set: bool
    lat_lon_waypoints: list[activity_streams_contracts.LatLonWaypoint]
    laps: list[activity_file_import_fit_frames.FitLap]
    splits: list[FitSplit]
    split_summary: list[activity_file_import_fit_frames.FitSplitSummary]
    sets: list[list[object]]
    workout_steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate]
    lengths: list[activity_file_import_fit_frames.FitLength]
    file_id: activity_file_import_fit_frames.FitFileId
    intraday_steps: list[activity_file_import_fit_frames.FitMonitoringSteps]
    intraday_heart_rate: list[activity_file_import_fit_frames.FitMonitoringHeartRate]
    resting_heart_rate: activity_file_import_fit_frames.FitRestingHeartRate | None
    exercise_titles: list[activity_exercise_titles_contracts.ActivityExerciseTitlesCreate]


class FitSessionRecord(TypedDict):
    """One activity of a FIT file: its session and the file's data within the session's time range.

    Attributes:
        session: The session summary.
        time_offset: The file's ``device_settings`` UTC offset in seconds.
        activity_time_offset: The file's ``activity`` message UTC offset in seconds, when it carries one.
        activity_name: The workout name, or the override.
        laps: The laps that start within the session.
        split_summary: The file's split summaries.
        workout_steps: The file's workout steps.
        sets: The file's workout sets.
        lengths: The file's pool lengths.
        file_id: The file's identification.
    """

    session: FitSession
    time_offset: int | None
    activity_time_offset: int | None
    activity_name: str
    lat_lon_waypoints: list[activity_streams_contracts.LatLonWaypoint]
    is_lat_lon_set: bool
    ele_waypoints: list[activity_streams_contracts.ElevationWaypoint]
    is_elevation_set: bool
    hr_waypoints: list[activity_streams_contracts.HeartRateWaypoint]
    is_heart_rate_set: bool
    cad_waypoints: list[activity_streams_contracts.CadenceWaypoint]
    is_cadence_set: bool
    power_waypoints: list[activity_streams_contracts.PowerWaypoint]
    is_power_set: bool
    vel_waypoints: list[activity_streams_contracts.VelocityWaypoint]
    pace_waypoints: list[activity_streams_contracts.PaceWaypoint]
    is_velocity_set: bool
    temp_waypoints: list[activity_streams_contracts.TemperatureWaypoint]
    is_temperature_set: bool
    laps: list[activity_file_import_fit_frames.FitLap]
    split_summary: list[activity_file_import_fit_frames.FitSplitSummary]
    workout_steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate]
    sets: list[list[object]]
    lengths: list[activity_file_import_fit_frames.FitLength]
    file_id: activity_file_import_fit_frames.FitFileId


def _fill_missing_lap_elevation(
    laps: list[activity_file_import_fit_frames.FitLap],
    ele_waypoints: Sequence[activity_streams_contracts.ElevationWaypoint],
) -> None:
    """Fill lap ascent/descent missing from the FIT lap frames.

    Some exporters (e.g. Health Sync) omit total_ascent/total_descent from lap
    frames. Compute them from the once-smoothed altitude record stream, like
    the GPX/TCX importers. Device-reported values (including a genuine 0) are
    never overridden.

    Args:
        laps: Lap dicts from parse_frame_lap; updated in place.
        ele_waypoints: Altitude record stream dicts with time/ele keys.
    """
    if not ele_waypoints or not all(isinstance(wp.get("ele"), int | float) for wp in ele_waypoints):
        return

    laps_to_fill = [
        (lap, start, elapsed)
        for lap in laps
        if (lap.get("total_ascent") is None or lap.get("total_descent") is None)
        and (start := lap.get("start_time")) is not None
        and (elapsed := lap.get("total_elapsed_time")) is not None
    ]
    if not laps_to_fill:
        return

    smoothed = activities_computation.smooth_elevation_stream(ele_waypoints)

    for lap, start, elapsed in laps_to_fill:
        end = start + timedelta(seconds=elapsed)
        lap_ele = activity_file_import_parser_utils.slice_lap_elevation(
            smoothed,
            core_timezone.format_utc(start),
            core_timezone.format_utc(end),
        )
        if not lap_ele:
            continue
        ele_gain, ele_loss = activities_computation.sum_elevation_deltas(lap_ele)
        if lap.get("total_ascent") is None:
            lap["total_ascent"] = round(ele_gain)
        if lap.get("total_descent") is None:
            lap["total_descent"] = round(ele_loss)


def create_activity_objects(
    sessions_records: list[FitSessionRecord],
    user_id: uuid.UUID,
    default_timezone: str,
) -> list[activity_file_import_parser_utils.ActivityFilePayload[activity_file_import_fit_frames.FitLap]]:
    """Build per-activity parsed payloads from the split FIT session records.

    Pure: derives everything from the FIT bytes. Privacy defaults, gear, and the
    Garmin provider ids are re-attached later by the ``activity_ingestion``
    enrichment seam.

    Args:
        sessions_records: Parsed FIT session records.
        user_id: ID of the user the activities belong to.
        default_timezone: Timezone to assume when the file carries none.

    Returns:
        One parsed payload per activity.
    """
    try:
        logger.debug(
            "FIT: building activity objects",
            extra=core_logger.context(user_id=user_id, sessions=len(sessions_records)),
        )
        # Fallback for sessions with neither a GPS track nor a reported UTC
        # offset (indoor rides, treadmill runs, pool swims).
        timezone = default_timezone

        activities: list[
            activity_file_import_parser_utils.ActivityFilePayload[activity_file_import_fit_frames.FitLap]
        ] = []

        for session_record in sessions_records:
            # Define default values
            activity_type = 10
            activity_name = activity_constants.DEFAULT_ACTIVITY_NAME
            pace: float = 0
            # Resolve each session's timezone from scratch. Reusing the loop
            # variable let a session with neither GPS nor a time offset inherit
            # the PREVIOUS session's timezone, which silently mislabelled every
            # activity after the first in a multi-activity .fit file.
            session_timezone = timezone

            if session_record["session"]["activity_type"]:
                # Set the activity type based on the session record
                activity_type = activity_constants.define_activity_type(str(session_record["session"]["activity_type"]))

            if (
                session_record["activity_name"]
                and session_record["activity_name"] != activity_constants.DEFAULT_ACTIVITY_NAME
            ):
                activity_name = session_record["activity_name"]

            # Resolve the summary distance. FIT stores it on the session frame,
            # but some sources omit total_distance even when the activity has a
            # GPS track or an average speed. Fall back so distance (and the pace
            # derived from it) are not left at zero when they are recoverable.
            resolved_distance = session_record["session"]["distance"]
            if not resolved_distance and session_record["is_lat_lon_set"]:
                resolved_distance = activity_file_import_parser_utils.compute_distance_from_waypoints(
                    session_record["lat_lon_waypoints"]
                )
            if not resolved_distance:
                avg_speed = session_record["session"]["avg_speed"]
                timer_time = session_record["session"]["total_timer_time"]
                if avg_speed and timer_time:
                    resolved_distance = avg_speed * timer_time

            # Calculate elevation gain/loss, pace, average speed, and average power
            total_timer_time, pace = activity_file_import_fit_frames.calculate_pace(
                resolved_distance,
                session_record["session"]["total_timer_time"],
                session_record["session"]["activity_type"],
                session_record["split_summary"],
                session_record["lengths"],
            )

            if activity_type not in activity_constants.VIRTUAL_ACTIVITY_TYPES:
                if session_record["is_lat_lon_set"]:
                    session_timezone = activity_file_import_parser_utils.resolve_timezone_from_lat_lon(
                        session_record["lat_lon_waypoints"][0]["lat"],
                        session_record["lat_lon_waypoints"][0]["lon"],
                        timezone,
                    )
                elif (activity_time_offset := session_record.get("activity_time_offset")) is not None and (
                    activity_time_offset != 0 or not session_record["time_offset"]
                ):
                    # activity.local_timestamp - activity.timestamp is the
                    # canonical FIT offset and is present in GPS-less files,
                    # so it outranks device_settings.time_offset. Some writers
                    # set local_timestamp == timestamp when the zone is
                    # unknown, so a 0 offset yields to a non-zero
                    # device_settings.time_offset.
                    session_timezone = activity_file_import_fit_frames._timezone_from_offset(
                        activity_time_offset,
                        session_record["session"]["first_waypoint_time"],
                        default_timezone,
                        timezone,
                    )
                elif time_offset := session_record["time_offset"]:
                    session_timezone = activity_file_import_fit_frames._timezone_from_offset(
                        time_offset,
                        session_record["session"]["first_waypoint_time"],
                        default_timezone,
                        timezone,
                    )

            avg_power: float | None = session_record["session"]["avg_power"]
            max_power: float | None = session_record["session"]["max_power"]
            np_power: float | None = session_record["session"]["np"]
            if session_record["is_power_set"] and (avg_power is None or np_power is None):
                calc_avg, calc_max, calc_np = activity_file_import_parser_utils.calculate_power_metrics(
                    session_record["power_waypoints"]
                )
                if avg_power is None:
                    avg_power = calc_avg
                    max_power = calc_max
                if np_power is None:
                    np_power = calc_np

            # Recompute avg/max HR from waypoints, excluding zeros (zero is not a
            # valid HR value — it means the sensor was disconnected). This overrides
            # the device-computed session value which may include zero-readings.
            session_avg_hr = session_record["session"]["avg_hr"]
            session_max_hr = session_record["session"]["max_hr"]
            if session_record.get("hr_waypoints"):
                recomputed_avg, recomputed_max = activities_computation.calculate_avg_and_max(
                    session_record["hr_waypoints"],
                    "hr",
                )
                if recomputed_avg:
                    session_avg_hr = round(recomputed_avg)
                if recomputed_max:
                    session_max_hr = round(recomputed_max)

            # Fall back to a computed speed when the session omitted
            # avg/max speed. Use distance/moving-time for the average
            # (the basis trackers use) and GPS velocity waypoints for
            # the maximum. Values are in m/s to match the schema.
            avg_speed = session_record["session"]["avg_speed"]
            max_speed = session_record["session"]["max_speed"]
            if avg_speed is None and pace:
                # pace is s/m (moving_time / distance); invert to m/s.
                avg_speed = 1 / pace
            if (avg_speed is None or max_speed is None) and session_record["vel_waypoints"]:
                vel_avg, vel_max = activities_computation.calculate_avg_and_max(
                    session_record["vel_waypoints"],
                    "vel",
                )
                vel_max = activities_computation.calculate_robust_max(
                    [waypoint["vel"] for waypoint in session_record["vel_waypoints"]],
                )
                if avg_speed is None and vel_avg:
                    avg_speed = vel_avg
                if max_speed is None and vel_max:
                    max_speed = vel_max

            # FIT running cadence is a single-leg rate (rpm) plus a
            # fractional_cadence, so running types are stored as steps per
            # minute: spm = (cadence + fractional) * 2. Other sports keep their
            # native rpm. Falls back to the per-record stream (read here, before
            # it is doubled below) when the session avg/max cadence is missing
            # or zero.
            avg_cadence: float | None = session_record["session"]["avg_cadence"]
            max_cadence: float | None = session_record["session"]["max_cadence"]
            if (not avg_cadence or not max_cadence) and session_record["cad_waypoints"]:
                cad_avg, cad_max = activities_computation.calculate_avg_and_max(
                    session_record["cad_waypoints"],
                    "cad",
                )
                if not avg_cadence and cad_avg:
                    avg_cadence = cad_avg
                if not max_cadence and cad_max:
                    max_cadence = cad_max
            double_cadence = activity_constants.is_running_cadence_type(activity_type)
            if double_cadence:
                avg_cadence = activities_computation.double_running_cadence(
                    avg_cadence, session_record["session"].get("avg_fractional_cadence")
                )
                max_cadence = activities_computation.double_running_cadence(
                    max_cadence, session_record["session"].get("max_fractional_cadence")
                )
            else:
                avg_cadence = round(avg_cadence) if avg_cadence is not None else None
                max_cadence = round(max_cadence) if max_cadence is not None else None

            # Fall back to elevation gain/loss computed from the elevation
            # stream when the session omitted them but elevation exists.
            ele_gain = session_record["session"]["ele_gain"]
            ele_loss = session_record["session"]["ele_loss"]
            if (ele_gain is None or ele_loss is None) and session_record["ele_waypoints"]:
                computed_gain, computed_loss = activities_computation.compute_elevation_gain_and_loss(
                    elevations=session_record["ele_waypoints"],
                )
                # A computed 0 m on a flat ride is a real value, not missing data.
                if ele_gain is None and computed_gain is not None:
                    ele_gain = round(computed_gain)
                if ele_loss is None and computed_loss is not None:
                    ele_loss = round(computed_loss)

            activity = activity_contracts.ActivityCore(
                user_id=user_id,
                name=activity_name,
                distance=(round(resolved_distance) if resolved_distance else 0),
                activity_type=activity_constants.ActivityType.from_stored(activity_type),
                start_time=core_timezone.to_utc_second(session_record["session"]["first_waypoint_time"]),
                end_time=core_timezone.to_utc_second(session_record["session"]["last_waypoint_time"]),
                timezone=session_timezone,
                total_elapsed_time=session_record["session"]["total_elapsed_time"],
                total_timer_time=total_timer_time,
                city=session_record["session"]["city"],
                town=session_record["session"]["town"],
                country=session_record["session"]["country"],
                elevation_gain=ele_gain,
                elevation_loss=ele_loss,
                pace=pace,
                average_speed=avg_speed,
                max_speed=max_speed,
                average_power=round(avg_power) if avg_power else None,
                max_power=round(max_power) if max_power else None,
                normalized_power=round(np_power) if np_power else None,
                average_hr=session_avg_hr,
                max_hr=session_max_hr,
                average_cad=avg_cadence,
                max_cad=max_cadence,
                workout_feeling=session_record["session"]["workout_feeling"],
                workout_rpe=session_record["session"]["workout_rpe"],
                calories=session_record["session"]["calories"],
                strava_gear_id=None,
                strava_activity_id=None,
                tracker_manufacturer=(
                    str(manufacturer)
                    if (manufacturer := session_record["file_id"].get("manufacturer")) is not None
                    else None
                ),
                tracker_model=(str(model) if (model := session_record["file_id"].get("product")) is not None else None),
                total_cycles=session_record["session"]["total_cycles"],
            )

            _fill_missing_lap_elevation(
                session_record["laps"],
                session_record["ele_waypoints"],
            )

            # The per-record stream and the laps follow avg/max to spm. The
            # lap fraction is folded into avg/max_cadence, so the fractional
            # columns are cleared rather than left holding per-leg values.
            if double_cadence:
                session_record["cad_waypoints"] = activities_computation.double_cadence_waypoints(
                    session_record["cad_waypoints"]
                )
                for lap in session_record["laps"]:
                    lap["avg_cadence"] = activities_computation.double_running_cadence(
                        lap.get("avg_cadence"), lap.get("avg_fractional_cadence")
                    )
                    lap["max_cadence"] = activities_computation.double_running_cadence(
                        lap.get("max_cadence"), lap.get("max_fractional_cadence")
                    )
                    lap["avg_fractional_cadence"] = None
                    lap["max_fractional_cadence"] = None

            waypoints: activity_file_import_parser_utils.ActivityWaypoints = {
                "ele_waypoints": session_record["ele_waypoints"],
                "power_waypoints": session_record["power_waypoints"],
                "hr_waypoints": session_record["hr_waypoints"],
                "vel_waypoints": session_record["vel_waypoints"],
                "pace_waypoints": session_record["pace_waypoints"],
                "cad_waypoints": session_record["cad_waypoints"],
                "lat_lon_waypoints": session_record["lat_lon_waypoints"],
                "temp_waypoints": session_record.get("temp_waypoints", []),
            }
            extras: activity_file_import_parser_utils.ActivityFileExtras = {
                "sets": session_record["sets"],
                "workout_steps": session_record["workout_steps"],
            }
            parsed_activity = activity_file_import_parser_utils.build_activity_file_payload(
                activity,
                waypoints,
                session_record["laps"],
                extras,
            )

            activities.append(parsed_activity)

        logger.debug(
            "FIT: built activity objects",
            extra=core_logger.context(user_id=user_id, activity_count=len(activities)),
        )
        return activities
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        # Any other failure on these bytes recurs on every retry, so the file is refused rather than retried;
        # the traceback is kept at WARNING in case the parser itself is at fault.
        logger.warning(
            "Could not build activities from a FIT file", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.InvalidInputError("Can't parse FIT file sessions") from err


def split_records_by_activity(parsed_data: FitParsePayload) -> list[FitSessionRecord]:
    """Split parsed FIT records into one payload per session.

    Args:
        parsed_data: The parsed FIT dict with sessions and waypoint streams.

    Returns:
        One payload dict per activity session.
    """
    sessions = parsed_data["sessions"]
    lat_lon_waypoints = parsed_data["lat_lon_waypoints"]
    ele_waypoints = parsed_data.get("ele_waypoints", [])
    hr_waypoints = parsed_data.get("hr_waypoints", [])
    cad_waypoints = parsed_data.get("cad_waypoints", [])
    power_waypoints = parsed_data.get("power_waypoints", [])
    vel_waypoints = parsed_data.get("vel_waypoints", [])
    pace_waypoints = parsed_data.get("pace_waypoints", [])
    temp_waypoints = parsed_data.get("temp_waypoints", [])

    # Check for each auxiliary flag
    is_lat_lon_set = parsed_data.get("is_lat_lon_set", False)
    is_elevation_set = parsed_data.get("is_elevation_set", False)
    is_heart_rate_set = parsed_data.get("is_heart_rate_set", False)
    is_cadence_set = parsed_data.get("is_cadence_set", False)
    is_power_set = parsed_data.get("is_power_set", False)
    is_velocity_set = parsed_data.get("is_velocity_set", False)
    is_temperature_set = parsed_data.get("is_temperature_set", False)

    sessions_records: list[FitSessionRecord] = []

    # Convert session times to datetime objects for easier comparison
    for session in sessions:
        # Use the time as is if it is already a datetime object; otherwise, parse it
        start_time = session["first_waypoint_time"]
        if not isinstance(start_time, datetime):
            start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
        # Ensure tz-aware for consistent comparisons
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)

        end_time = session.get("last_waypoint_time", start_time)
        if not isinstance(end_time, datetime):
            end_time = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=UTC)

        laps_records: list[activity_file_import_fit_frames.FitLap] = []

        if parsed_data["laps"]:
            for lap in parsed_data["laps"]:
                # Skip laps with no start time
                lap_start_time = lap["start_time"]
                if lap_start_time is None:
                    continue
                # Check if the lap's start time is within the session's start and end times
                if start_time <= lap_start_time <= end_time:
                    # Append the lap to the session's laps
                    laps_records.append(lap)

        # Initialize a parsed session dictionary
        parsed_session: FitSessionRecord = {
            "session": session,
            "time_offset": parsed_data["time_offset"],
            "activity_time_offset": parsed_data.get("activity_time_offset"),
            "activity_name": parsed_data["activity_name"],
            "lat_lon_waypoints": [],
            "is_lat_lon_set": False,
            "ele_waypoints": [],
            "is_elevation_set": False,
            "hr_waypoints": [],
            "is_heart_rate_set": False,
            "cad_waypoints": [],
            "is_cadence_set": False,
            "power_waypoints": [],
            "is_power_set": False,
            "vel_waypoints": [],
            "pace_waypoints": [],
            "is_velocity_set": False,
            "temp_waypoints": [],
            "is_temperature_set": False,
            "laps": laps_records,
            "split_summary": parsed_data["split_summary"],
            "workout_steps": parsed_data["workout_steps"],
            "sets": parsed_data["sets"],
            "lengths": parsed_data["lengths"],
            "file_id": parsed_data["file_id"],
        }

        # Each stream flagged as set is cut to the session's time range.
        # If there are waypoints, set the parsed session's waypoints and flag
        if is_lat_lon_set and (
            session_lat_lon := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                lat_lon_waypoints, start_time, end_time
            )
        ):
            parsed_session["lat_lon_waypoints"] = session_lat_lon
            parsed_session["is_lat_lon_set"] = True

            # If initial latitude and longitude are not set, set them
            # to the first waypoint's coordinates
            if (
                parsed_session["session"]["initial_latitude"] is None
                or parsed_session["session"]["initial_longitude"] is None
            ):
                parsed_session["session"]["initial_latitude"] = session_lat_lon[0]["lat"]
                parsed_session["session"]["initial_longitude"] = session_lat_lon[0]["lon"]

        if is_elevation_set and (
            session_ele := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                ele_waypoints, start_time, end_time
            )
        ):
            parsed_session["ele_waypoints"] = session_ele
            parsed_session["is_elevation_set"] = True

        if is_heart_rate_set and (
            session_hr := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                hr_waypoints, start_time, end_time
            )
        ):
            parsed_session["hr_waypoints"] = session_hr
            parsed_session["is_heart_rate_set"] = True

        if is_cadence_set and (
            session_cad := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                cad_waypoints, start_time, end_time
            )
        ):
            parsed_session["cad_waypoints"] = session_cad
            parsed_session["is_cadence_set"] = True

        if is_power_set and (
            session_power := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                power_waypoints, start_time, end_time
            )
        ):
            parsed_session["power_waypoints"] = session_power
            parsed_session["is_power_set"] = True

        if is_velocity_set:
            if session_vel := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                vel_waypoints, start_time, end_time
            ):
                parsed_session["vel_waypoints"] = session_vel
                parsed_session["is_velocity_set"] = True
            if session_pace := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                pace_waypoints, start_time, end_time
            ):
                parsed_session["pace_waypoints"] = session_pace
                parsed_session["is_velocity_set"] = True

        if is_temperature_set and (
            session_temp := activity_file_import_parser_utils.filter_waypoints_by_datetime_range(
                temp_waypoints, start_time, end_time
            )
        ):
            parsed_session["temp_waypoints"] = session_temp
            parsed_session["is_temperature_set"] = True

        # Append the parsed session to the sessions list
        sessions_records.append(parsed_session)

    return sessions_records


@dataclass
class FitParseState:
    """Mutable state accumulated while parsing a FIT file.

    Groups the FIT-specific session/lap/split collections together with
    the GPX-style waypoint streams, presence flags, and the per-record
    cursors used to compute instant speed.
    """

    activity_name: str = activity_constants.DEFAULT_ACTIVITY_NAME
    time_offset: int | None = 0
    activity_time_offset: int | None = None
    last_waypoint_time: datetime | None = None
    resting_heart_rate: activity_file_import_fit_frames.FitRestingHeartRate | None = None
    sessions: list[FitSession] = field(default_factory=list)
    laps: list[activity_file_import_fit_frames.FitLap] = field(default_factory=list)
    splits: list[FitSplit] = field(default_factory=list)
    split_summary: list[activity_file_import_fit_frames.FitSplitSummary] = field(default_factory=list)
    sets: list[list[object]] = field(default_factory=list)
    workout_steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate] = field(default_factory=list)
    exercises_titles: list[activity_exercise_titles_contracts.ActivityExerciseTitlesCreate] = field(
        default_factory=list
    )
    lengths: list[activity_file_import_fit_frames.FitLength] = field(default_factory=list)
    intraday_steps: list[activity_file_import_fit_frames.FitMonitoringSteps] = field(default_factory=list)
    intraday_heart_rate: list[activity_file_import_fit_frames.FitMonitoringHeartRate] = field(default_factory=list)
    # Empty until the file's file_id message is read.
    file_id: activity_file_import_fit_frames.FitFileId = field(
        default_factory=activity_file_import_fit_frames.FitFileId
    )
    lat_lon_waypoints: list[activity_streams_contracts.LatLonWaypoint] = field(default_factory=list)
    ele_waypoints: list[activity_streams_contracts.ElevationWaypoint] = field(default_factory=list)
    hr_waypoints: list[activity_streams_contracts.HeartRateWaypoint] = field(default_factory=list)
    cad_waypoints: list[activity_streams_contracts.CadenceWaypoint] = field(default_factory=list)
    power_waypoints: list[activity_streams_contracts.PowerWaypoint] = field(default_factory=list)
    vel_waypoints: list[activity_streams_contracts.VelocityWaypoint] = field(default_factory=list)
    pace_waypoints: list[activity_streams_contracts.PaceWaypoint] = field(default_factory=list)
    temp_waypoints: list[activity_streams_contracts.TemperatureWaypoint] = field(default_factory=list)
    prev_latitude: float | None = None
    prev_longitude: float | None = None
    is_lat_lon_set: bool = False
    is_elevation_set: bool = False
    is_power_set: bool = False
    is_heart_rate_set: bool = False
    is_cadence_set: bool = False
    is_velocity_set: bool = False
    is_temperature_set: bool = False

    def reset_record_cursor(self) -> None:
        """Clear cursors that must not bridge across FIT sessions."""
        self.prev_latitude = None
        self.prev_longitude = None
        self.last_waypoint_time = None

    def to_payload(self) -> FitParsePayload:
        """Return the parser output dict expected by downstream callers.

        Returns:
            The payload dict.
        """
        return {
            "sessions": self.sessions,
            "time_offset": self.time_offset,
            "activity_time_offset": self.activity_time_offset,
            "activity_name": self.activity_name,
            "is_elevation_set": self.is_elevation_set,
            "ele_waypoints": self.ele_waypoints,
            "is_power_set": self.is_power_set,
            "power_waypoints": self.power_waypoints,
            "is_heart_rate_set": self.is_heart_rate_set,
            "hr_waypoints": self.hr_waypoints,
            "is_velocity_set": self.is_velocity_set,
            "vel_waypoints": self.vel_waypoints,
            "pace_waypoints": self.pace_waypoints,
            "is_temperature_set": self.is_temperature_set,
            "temp_waypoints": self.temp_waypoints,
            "is_cadence_set": self.is_cadence_set,
            "cad_waypoints": self.cad_waypoints,
            "is_lat_lon_set": self.is_lat_lon_set,
            "lat_lon_waypoints": self.lat_lon_waypoints,
            "laps": self.laps,
            "splits": self.splits,
            "split_summary": self.split_summary,
            "sets": self.sets,
            "workout_steps": self.workout_steps,
            "lengths": self.lengths,
            "file_id": self.file_id,
            "intraday_steps": self.intraday_steps,
            "intraday_heart_rate": self.intraday_heart_rate,
            "resting_heart_rate": self.resting_heart_rate,
            "exercise_titles": self.exercises_titles,
        }


def _handle_session_frame(frame: fitdecode.FitDataMessage, state: FitParseState) -> None:
    """Parse a session frame, geocode it, and reset per-record cursors.

    Args:
        frame: The decoded FIT session message.
        state: Mutable parse state for the current file.
    """
    (
        initial_latitude,
        initial_longitude,
        activity_type,
        first_waypoint_time,
        total_elapsed_time,
        total_timer_time,
        calories,
        distance,
        avg_hr,
        max_hr,
        avg_cadence,
        max_cadence,
        avg_fractional_cadence,
        max_fractional_cadence,
        avg_power,
        max_power,
        ele_gain,
        ele_loss,
        np,
        avg_speed,
        max_speed,
        workout_feeling,
        workout_rpe,
        total_cycles,
    ) = activity_file_import_fit_frames.parse_frame_session(frame)

    city, town, country = None, None, None

    state.sessions.append(
        {
            "initial_latitude": initial_latitude,
            "initial_longitude": initial_longitude,
            "city": city,
            "town": town,
            "country": country,
            "activity_type": activity_type,
            "first_waypoint_time": first_waypoint_time,
            "last_waypoint_time": first_waypoint_time + timedelta(seconds=total_elapsed_time),
            "total_elapsed_time": total_elapsed_time,
            "total_timer_time": total_timer_time,
            "calories": calories,
            "distance": distance,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "avg_cadence": avg_cadence,
            "max_cadence": max_cadence,
            "avg_fractional_cadence": avg_fractional_cadence,
            "max_fractional_cadence": max_fractional_cadence,
            "avg_power": avg_power,
            "max_power": max_power,
            "ele_gain": ele_gain,
            "ele_loss": ele_loss,
            "np": np,
            "avg_speed": avg_speed,
            "max_speed": max_speed,
            "workout_feeling": workout_feeling,
            "workout_rpe": workout_rpe,
            "total_cycles": total_cycles,
        }
    )

    # FIT session messages are emitted at the end of each session. Reset the
    # per-record cursors so the first record of any subsequent session does
    # not compute distance/speed against the last record of the previous one.
    state.reset_record_cursor()


def _handle_split_frame(frame: fitdecode.FitDataMessage, state: FitParseState) -> None:
    """Parse a split frame and append it to state.

    Args:
        frame: The decoded FIT split message.
        state: Mutable parse state for the current file.
    """
    (
        split_type,
        total_elapsed_time,
        total_timer_time,
        total_distance,
        avg_speed,
        start_time,
        total_ascent,
        total_descent,
        start_position_lat,
        start_position_long,
        end_position_lat,
        end_position_long,
        max_speed,
        end_time,
        total_calories,
        start_elevation,
    ) = activity_file_import_fit_frames.parse_frame_split(frame)
    state.splits.append(
        {
            "split_type": split_type,
            "total_elapsed_time": total_elapsed_time,
            "total_timer_time": total_timer_time,
            "total_distance": total_distance,
            "avg_speed": avg_speed,
            "start_time": start_time,
            "total_ascent": total_ascent,
            "total_descent": total_descent,
            "start_position_lat": start_position_lat,
            "start_position_long": start_position_long,
            "end_position_lat": end_position_lat,
            "end_position_long": end_position_long,
            "max_speed": max_speed,
            "end_time": end_time,
            "total_calories": total_calories,
            "start_elevation": start_elevation,
        }
    )


def _handle_split_summary_frame(frame: fitdecode.FitDataMessage, state: FitParseState) -> None:
    """Parse a split_summary frame and append it to state.

    Args:
        frame: The decoded FIT split-summary message.
        state: Mutable parse state for the current file.
    """
    split_type, total_timer_time = activity_file_import_fit_frames.parse_frame_split_summary(frame)
    state.split_summary.append(
        {
            "split_type": split_type,
            "total_timer_time": total_timer_time,
        }
    )


def _handle_record_frame(frame: fitdecode.FitDataMessage, state: FitParseState) -> None:
    """Process a record frame into waypoint streams and presence flags.

    Args:
        frame: The decoded FIT record message.
        state: Mutable parse state for the current file.
    """
    (
        latitude,
        longitude,
        elevation,
        time,
        heart_rate,
        cadence,
        power,
        temperature,
    ) = activity_file_import_fit_frames.parse_frame_record(frame)

    if elevation is not None:
        state.is_elevation_set = True
    if heart_rate is not None:
        state.is_heart_rate_set = True
    if cadence is not None:
        state.is_cadence_set = True
    if power is not None:
        state.is_power_set = True
    if temperature is not None:
        state.is_temperature_set = True

    instant_speed = None
    if (
        latitude is not None
        and state.prev_latitude is not None
        and longitude is not None
        and state.prev_longitude is not None
    ):
        instant_speed = activities_computation.calculate_instant_speed(
            state.last_waypoint_time,
            time,
            latitude,
            longitude,
            state.prev_latitude,
            state.prev_longitude,
        )

    instant_pace = None
    if instant_speed:
        instant_pace = 1 / instant_speed
        state.is_velocity_set = True

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

    if latitude is not None and longitude is not None:
        state.lat_lon_waypoints.append({"time": timestamp, "lat": latitude, "lon": longitude})
        state.is_lat_lon_set = True

    if elevation is not None:
        state.ele_waypoints.append({"time": timestamp, "ele": elevation})
    if heart_rate is not None:
        state.hr_waypoints.append({"time": timestamp, "hr": heart_rate})
    if cadence is not None:
        state.cad_waypoints.append({"time": timestamp, "cad": cadence})
    if power is not None:
        state.power_waypoints.append({"time": timestamp, "power": power})
    if instant_speed is not None:
        state.vel_waypoints.append({"time": timestamp, "vel": instant_speed})
    if instant_pace is not None:
        state.pace_waypoints.append({"time": timestamp, "pace": instant_pace})
    if temperature is not None:
        state.temp_waypoints.append({"time": timestamp, "temp": temperature})

    state.prev_latitude = latitude
    state.prev_longitude = longitude
    state.last_waypoint_time = time


def _handle_monitoring_frame(frame: fitdecode.FitDataMessage, state: FitParseState, last_timestamp: int) -> None:
    """Parse a monitoring frame and extend intraday collections.

    Args:
        frame: The decoded FIT monitoring message.
        state: Mutable parse state for the current file.
        last_timestamp: Timestamp of the previous monitoring frame.
    """
    steps, heart_rate = activity_file_import_fit_frames.parse_frame_monitoring(frame, last_timestamp)
    state.intraday_steps.extend(steps)
    state.intraday_heart_rate.extend(heart_rate)


def _dispatch_data_message(frame: fitdecode.FitDataMessage, state: FitParseState, last_timestamp: int) -> None:
    """Route a FIT data message to the appropriate handler.

    Args:
        frame: The decoded FIT data message.
        state: Mutable parse state for the current file.
        last_timestamp: Timestamp of the previous monitoring frame.
    """
    name = frame.name
    if name == "session":
        _handle_session_frame(frame, state)
    elif name == "workout":
        state.activity_name = activity_file_import_fit_frames.parse_frame_workout(frame)
    elif name == "lap":
        state.laps.append(activity_file_import_fit_frames.parse_frame_lap(frame))
    elif name in {"split", "unknown_312"}:
        _handle_split_frame(frame, state)
    elif name in {"split_summary", "unknown_313"}:
        _handle_split_summary_frame(frame, state)
    elif name == "set":
        state.sets.append(activity_file_import_fit_frames.parse_frame_set(frame))
    elif name == "workout_step":
        state.workout_steps.append(activity_file_import_fit_frames.parse_frame_workout_step(frame))
    elif name == "exercise_title":
        exercise_title = activity_file_import_fit_frames.parse_frame_exercise_title(frame)
        if exercise_title is not None:
            state.exercises_titles.append(exercise_title)
    elif name == "record":
        _handle_record_frame(frame, state)
    elif name == "device_settings":
        state.time_offset = activity_file_import_fit_frames.interpret_time_offset(
            activity_file_import_fit_frames.parse_frame_device_settings(frame)
        )
    elif name == "activity":
        state.activity_time_offset = activity_file_import_fit_frames.parse_frame_activity(frame)
    elif name == "length":
        state.lengths.append(activity_file_import_fit_frames.parse_frame_length(frame))
    elif name == "file_id":
        state.file_id = activity_file_import_fit_frames.parse_frame_file_id(frame)
    elif name == "monitoring":
        _handle_monitoring_frame(frame, state, last_timestamp)
    elif name == "monitoring_hr_data":
        state.resting_heart_rate = activity_file_import_fit_frames.parse_frame_monitoring_hr_data(frame)


def parse_fit_file(file: str, activity_name_input: str | None = None) -> FitParsePayload:
    """Parse a FIT file into the parser's payload dict.

    Args:
        file: Path of the FIT file.
        activity_name_input: Optional activity name override.

    Returns:
        The payload dict consumed by the ingestion pipeline.

    Raises:
        InvalidInputError: When the content is not a valid FIT file or cannot be parsed.
        ProcessingError: When the file cannot be read.
    """
    try:
        logger.debug("FIT parse start", extra=core_logger.context(file=Path(file).name))
        state = FitParseState(
            activity_name=activity_name_input or activity_constants.DEFAULT_ACTIVITY_NAME,
        )

        with open(file, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    _dispatch_data_message(frame, state, fit_data.last_timestamp)

        logger.debug(
            "FIT parse complete",
            extra=core_logger.context(file=Path(file).name, exercise_titles=len(state.exercises_titles)),
        )
        return state.to_payload()
    except core_exceptions.DomainError:
        raise
    except fitdecode.FitError as err:
        # The uploader's file is the problem, so a retry reaches the same verdict.
        logger.debug("Rejected a malformed FIT file", exc_info=err, extra=core_logger.context(file=Path(file).name))
        raise core_exceptions.InvalidInputError("Can't parse FIT file") from err
    except OSError as err:
        logger.debug("Could not read a FIT file", exc_info=err, extra=core_logger.context(file=Path(file).name))
        raise core_exceptions.ProcessingError("Can't read FIT file") from err
    except Exception as err:
        # Any other failure on these bytes recurs on every retry, so the file is refused rather than retried;
        # the traceback is kept at WARNING in case the parser itself is at fault.
        logger.warning("Could not parse a FIT file", exc_info=err, extra=core_logger.context(file=Path(file).name))
        raise core_exceptions.InvalidInputError("Can't parse FIT file") from err
