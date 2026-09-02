from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fitdecode

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.constants as activities_constants
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity_file_import.utils as activity_file_import_utils
import modules.activities.activity_file_import.utils_fit_frames as fit_frames
import modules.activities.computation as activities_computation

logger = core_logger.get_logger(__name__)


def create_activity_objects(
    sessions_records: list[dict],
    user_id: int,
    default_timezone: str | None = None,
) -> list:
    """Build per-activity parsed payloads from the split FIT session records.

    Pure: derives everything from the FIT bytes. Privacy defaults, gear, and the
    Garmin provider ids are re-attached later by the ``activity_ingestion``
    enrichment seam.
    """
    try:
        logger.debug(
            "FIT: building activity objects",
            extra=core_logger.context(user_id=user_id, sessions=len(sessions_records)),
        )
        # Fallback for sessions with neither a GPS track nor a reported UTC
        # offset (indoor rides, treadmill runs, pool swims).
        timezone = default_timezone or core_config.settings.TZ

        activities = []

        for session_record in sessions_records:
            # Define default values
            activity_type = 10
            activity_name = "Workout"
            pace = 0
            # Resolve each session's timezone from scratch. Reusing the loop
            # variable let a session with neither GPS nor a time offset inherit
            # the PREVIOUS session's timezone, which silently mislabelled every
            # activity after the first in a multi-activity .fit file.
            session_timezone = timezone

            if session_record["session"]["activity_type"]:
                # Set the activity type based on the session record
                activity_type = activities_constants.define_activity_type(session_record["session"]["activity_type"])

            if session_record["activity_name"] and session_record["activity_name"] != "Workout":
                activity_name = session_record["activity_name"]

            # Resolve the summary distance. FIT stores it on the session frame,
            # but some sources omit total_distance even when the activity has a
            # GPS track or an average speed. Fall back so distance (and the pace
            # derived from it) are not left at zero when they are recoverable.
            resolved_distance = session_record["session"]["distance"]
            if not resolved_distance and session_record["is_lat_lon_set"]:
                resolved_distance = activity_file_import_utils.compute_distance_from_waypoints(
                    session_record["lat_lon_waypoints"]
                )
            if not resolved_distance:
                avg_speed = session_record["session"]["avg_speed"]
                timer_time = session_record["session"]["total_timer_time"]
                if avg_speed and timer_time:
                    resolved_distance = avg_speed * timer_time

            # Calculate elevation gain/loss, pace, average speed, and average power
            total_timer_time, pace = fit_frames.calculate_pace(
                resolved_distance,
                session_record["session"]["total_timer_time"],
                session_record["session"]["activity_type"],
                session_record["split_summary"],
                session_record["lengths"],
            )

            if activity_type not in activities_constants.VIRTUAL_ACTIVITY_TYPES:
                if session_record["is_lat_lon_set"]:
                    session_timezone = activity_file_import_utils.resolve_timezone_from_lat_lon(
                        session_record["lat_lon_waypoints"][0]["lat"],
                        session_record["lat_lon_waypoints"][0]["lon"],
                        timezone,
                    )
                elif session_record["time_offset"]:
                    session_timezone = fit_frames._timezone_from_offset(
                        session_record["time_offset"],
                        session_record["session"]["first_waypoint_time"],
                        default_timezone,
                        timezone,
                    )

            avg_power = session_record["session"]["avg_power"]
            max_power = session_record["session"]["max_power"]
            np_power = session_record["session"]["np"]
            if session_record["is_power_set"] and (avg_power is None or np_power is None):
                calc_avg, calc_max, calc_np = activity_file_import_utils.calculate_power_metrics(
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
                if avg_speed is None and vel_avg:
                    avg_speed = vel_avg
                if max_speed is None and vel_max:
                    max_speed = vel_max

            # Fall back to cadence from the per-record stream when the
            # session omitted avg/max cadence but cadence was recorded.
            avg_cadence = session_record["session"]["avg_cadence"]
            max_cadence = session_record["session"]["max_cadence"]
            if (avg_cadence is None or max_cadence is None) and session_record["cad_waypoints"]:
                cad_avg, cad_max = activities_computation.calculate_avg_and_max(
                    session_record["cad_waypoints"],
                    "cad",
                )
                if avg_cadence is None and cad_avg:
                    avg_cadence = round(cad_avg)
                if max_cadence is None and cad_max:
                    max_cadence = round(cad_max)

            # Fall back to elevation gain/loss computed from the elevation
            # stream when the session omitted them but elevation exists.
            ele_gain = session_record["session"]["ele_gain"]
            ele_loss = session_record["session"]["ele_loss"]
            if (ele_gain is None or ele_loss is None) and session_record["ele_waypoints"]:
                computed_gain, computed_loss = activities_computation.compute_elevation_gain_and_loss(
                    elevations=session_record["ele_waypoints"],
                )
                if ele_gain is None and computed_gain:
                    ele_gain = round(computed_gain)
                if ele_loss is None and computed_loss:
                    ele_loss = round(computed_loss)

            activity = activities_contracts.ActivityCore(
                user_id=user_id,
                name=activity_name,
                distance=(round(resolved_distance) if resolved_distance else 0),
                activity_type=activity_type,
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

            waypoints = {
                "ele_waypoints": session_record["ele_waypoints"],
                "power_waypoints": session_record["power_waypoints"],
                "hr_waypoints": session_record["hr_waypoints"],
                "vel_waypoints": session_record["vel_waypoints"],
                "pace_waypoints": session_record["pace_waypoints"],
                "cad_waypoints": session_record["cad_waypoints"],
                "lat_lon_waypoints": session_record["lat_lon_waypoints"],
                "temp_waypoints": session_record.get("temp_waypoints", []),
            }
            extras = {
                "sets": session_record["sets"],
                "workout_steps": session_record["workout_steps"],
            }
            parsed_activity = activity_file_import_utils.build_activity_file_payload(
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
        logger.error("Error in create_activity_objects", exc_info=err, extra=core_logger.context(user_id=user_id))
        raise core_exceptions.ProcessingError("Can't parse FIT file sessions") from err


def split_records_by_activity(parsed_data: dict) -> list[dict]:
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

    # Dictionary to hold split waypoints per activity
    activity_waypoints: dict[int, dict[str, list[dict] | None]] = {
        i: {
            "lat_lon_waypoints": [] if is_lat_lon_set else None,
            "ele_waypoints": [] if is_elevation_set else None,
            "hr_waypoints": [] if is_heart_rate_set else None,
            "cad_waypoints": [] if is_cadence_set else None,
            "power_waypoints": [] if is_power_set else None,
            "vel_waypoints": [] if is_velocity_set else None,
            "pace_waypoints": [] if is_velocity_set else None,
            "temp_waypoints": [] if is_temperature_set else None,
        }
        for i in range(len(sessions))
    }

    sessions_records: list[dict] = []

    # Convert session times to datetime objects for easier comparison
    for i, session in enumerate(sessions):
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

        laps_records = []

        if parsed_data["laps"]:
            for lap in parsed_data["laps"]:
                # Skip laps with no start time
                if lap["start_time"] is None:
                    continue
                # Check if the lap's start time is within the session's start and end times
                if start_time <= lap["start_time"] <= end_time:
                    # Append the lap to the session's laps
                    laps_records.append(lap)

        # Initialize a parsed session dictionary
        parsed_session = {
            "session": session,
            "time_offset": parsed_data["time_offset"],
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

        # Build the streams dict for streams that are flagged as set,
        # then filter all of them in one call.
        raw_streams: dict[str, list[dict]] = {}
        if is_lat_lon_set:
            raw_streams["lat_lon_waypoints"] = lat_lon_waypoints
        if is_elevation_set:
            raw_streams["ele_waypoints"] = ele_waypoints
        if is_heart_rate_set:
            raw_streams["hr_waypoints"] = hr_waypoints
        if is_cadence_set:
            raw_streams["cad_waypoints"] = cad_waypoints
        if is_power_set:
            raw_streams["power_waypoints"] = power_waypoints
        if is_velocity_set:
            raw_streams["vel_waypoints"] = vel_waypoints
            raw_streams["pace_waypoints"] = pace_waypoints
        if is_temperature_set:
            raw_streams["temp_waypoints"] = temp_waypoints

        filtered = activity_file_import_utils.filter_streams_by_time_range(raw_streams, start_time, end_time)

        if is_lat_lon_set:
            activity_waypoints[i]["lat_lon_waypoints"] = filtered["lat_lon_waypoints"]
            # If there are waypoints, set the parsed session's waypoints and flag
            if filtered["lat_lon_waypoints"]:
                parsed_session["lat_lon_waypoints"] = filtered["lat_lon_waypoints"]
                parsed_session["is_lat_lon_set"] = True

                # If initial latitude and longitude are not set, set them
                # to the first waypoint's coordinates
                if (
                    parsed_session["session"]["initial_latitude"] is None
                    or parsed_session["session"]["initial_longitude"] is None
                ):
                    parsed_session["session"]["initial_latitude"] = filtered["lat_lon_waypoints"][0]["lat"]
                    parsed_session["session"]["initial_longitude"] = filtered["lat_lon_waypoints"][0]["lon"]

        if is_elevation_set:
            activity_waypoints[i]["ele_waypoints"] = filtered["ele_waypoints"]
            if filtered["ele_waypoints"]:
                parsed_session["ele_waypoints"] = filtered["ele_waypoints"]
                parsed_session["is_elevation_set"] = True

        if is_heart_rate_set:
            activity_waypoints[i]["hr_waypoints"] = filtered["hr_waypoints"]
            if filtered["hr_waypoints"]:
                parsed_session["hr_waypoints"] = filtered["hr_waypoints"]
                parsed_session["is_heart_rate_set"] = True

        if is_cadence_set:
            activity_waypoints[i]["cad_waypoints"] = filtered["cad_waypoints"]
            if filtered["cad_waypoints"]:
                parsed_session["cad_waypoints"] = filtered["cad_waypoints"]
                parsed_session["is_cadence_set"] = True

        if is_power_set:
            activity_waypoints[i]["power_waypoints"] = filtered["power_waypoints"]
            if filtered["power_waypoints"]:
                parsed_session["power_waypoints"] = filtered["power_waypoints"]
                parsed_session["is_power_set"] = True

        if is_velocity_set:
            activity_waypoints[i]["vel_waypoints"] = filtered["vel_waypoints"]
            if filtered["vel_waypoints"]:
                parsed_session["vel_waypoints"] = filtered["vel_waypoints"]
                parsed_session["is_velocity_set"] = True
            activity_waypoints[i]["pace_waypoints"] = filtered["pace_waypoints"]
            if filtered["pace_waypoints"]:
                parsed_session["pace_waypoints"] = filtered["pace_waypoints"]
                parsed_session["is_velocity_set"] = True

        if is_temperature_set:
            activity_waypoints[i]["temp_waypoints"] = filtered["temp_waypoints"]
            if filtered["temp_waypoints"]:
                parsed_session["temp_waypoints"] = filtered["temp_waypoints"]
                parsed_session["is_temperature_set"] = True

        # Append the parsed session to the sessions list
        sessions_records.append(parsed_session)

    # Return dictionary with each activity's waypoints
    return sessions_records


@dataclass
class FitParseState:
    """
    Mutable state accumulated while parsing a FIT file.

    Groups the FIT-specific session/lap/split collections together with
    the GPX-style waypoint streams, presence flags, and the per-record
    cursors used to compute instant speed.
    """

    activity_name: str = "Workout"
    time_offset: int = 0
    last_waypoint_time: datetime | None = None
    resting_heart_rate: dict | None = None
    sessions: list[dict] = field(default_factory=list)
    laps: list[dict] = field(default_factory=list)
    splits: list[dict] = field(default_factory=list)
    split_summary: list[dict] = field(default_factory=list)
    sets: list[list] = field(default_factory=list)
    workout_steps: list = field(default_factory=list)
    exercises_titles: list = field(default_factory=list)
    lengths: list[dict] = field(default_factory=list)
    intraday_steps: list[dict] = field(default_factory=list)
    intraday_heart_rate: list[dict] = field(default_factory=list)
    file_id: dict = field(default_factory=dict)
    lat_lon_waypoints: list[dict] = field(default_factory=list)
    ele_waypoints: list[dict] = field(default_factory=list)
    hr_waypoints: list[dict] = field(default_factory=list)
    cad_waypoints: list[dict] = field(default_factory=list)
    power_waypoints: list[dict] = field(default_factory=list)
    vel_waypoints: list[dict] = field(default_factory=list)
    pace_waypoints: list[dict] = field(default_factory=list)
    temp_waypoints: list[dict] = field(default_factory=list)
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

    def to_payload(self) -> dict:
        """Return the parser output dict expected by downstream callers."""
        return {
            "sessions": self.sessions,
            "time_offset": self.time_offset,
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


_SPLIT_KEYS = (
    "split_type",
    "total_elapsed_time",
    "total_timer_time",
    "total_distance",
    "avg_speed",
    "start_time",
    "total_ascent",
    "total_descent",
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "max_speed",
    "end_time",
    "total_calories",
    "start_elevation",
)


def _handle_session_frame(frame, state: FitParseState) -> None:
    """Parse a session frame, geocode it, and reset per-record cursors."""
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
    ) = fit_frames.parse_frame_session(frame)

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


def _handle_split_frame(frame, state: FitParseState) -> None:
    """Parse a split frame and append it to state."""
    split_data = fit_frames.parse_frame_split(frame)
    state.splits.append(dict(zip(_SPLIT_KEYS, split_data, strict=False)))


def _handle_split_summary_frame(frame, state: FitParseState) -> None:
    """Parse a split_summary frame and append it to state."""
    split_type, total_timer_time = fit_frames.parse_frame_split_summary(frame)
    state.split_summary.append(
        {
            "split_type": split_type,
            "total_timer_time": total_timer_time,
        }
    )


def _handle_record_frame(frame, state: FitParseState) -> None:
    """Process a record frame into waypoint streams and presence flags."""
    (
        latitude,
        longitude,
        elevation,
        time,
        heart_rate,
        cadence,
        power,
        temperature,
    ) = fit_frames.parse_frame_record(frame)

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

    activities_computation.append_if_not_none(state.ele_waypoints, timestamp, elevation, "ele")
    activities_computation.append_if_not_none(state.hr_waypoints, timestamp, heart_rate, "hr")
    activities_computation.append_if_not_none(state.cad_waypoints, timestamp, cadence, "cad")
    activities_computation.append_if_not_none(state.power_waypoints, timestamp, power, "power")
    activities_computation.append_if_not_none(state.vel_waypoints, timestamp, instant_speed, "vel")
    activities_computation.append_if_not_none(state.pace_waypoints, timestamp, instant_pace, "pace")
    activities_computation.append_if_not_none(state.temp_waypoints, timestamp, temperature, "temp")

    state.prev_latitude = latitude
    state.prev_longitude = longitude
    state.last_waypoint_time = time


def _handle_monitoring_frame(frame, state: FitParseState, last_timestamp) -> None:
    """Parse a monitoring frame and extend intraday collections."""
    steps, heart_rate = fit_frames.parse_frame_monitoring(frame, last_timestamp)
    state.intraday_steps.extend(steps)
    state.intraday_heart_rate.extend(heart_rate)


def _dispatch_data_message(frame, state: FitParseState, last_timestamp) -> None:
    """Route a FIT data message to the appropriate handler."""
    name = frame.name
    if name == "session":
        _handle_session_frame(frame, state)
    elif name == "workout":
        state.activity_name = fit_frames.parse_frame_workout(frame)
    elif name == "lap":
        state.laps.append(fit_frames.parse_frame_lap(frame))
    elif name in {"split", "unknown_312"}:
        _handle_split_frame(frame, state)
    elif name in {"split_summary", "unknown_313"}:
        _handle_split_summary_frame(frame, state)
    elif name == "set":
        state.sets.append(fit_frames.parse_frame_set(frame))
    elif name == "workout_step":
        state.workout_steps.append(fit_frames.parse_frame_workout_step(frame))
    elif name == "exercise_title":
        state.exercises_titles.append(fit_frames.parse_frame_exercise_title(frame))
    elif name == "record":
        _handle_record_frame(frame, state)
    elif name == "device_settings":
        state.time_offset = fit_frames.interpret_time_offset(fit_frames.parse_frame_device_settings(frame))
    elif name == "length":
        state.lengths.append(fit_frames.parse_frame_length(frame))
    elif name == "file_id":
        state.file_id = fit_frames.parse_frame_file_id(frame)
    elif name == "monitoring":
        _handle_monitoring_frame(frame, state, last_timestamp)
    elif name == "monitoring_hr_data":
        state.resting_heart_rate = fit_frames.parse_frame_monitoring_hr_data(frame)


def parse_fit_file(file: str, activity_name_input: str | None = None) -> dict:
    try:
        logger.debug("FIT parse start", extra=core_logger.context(file=Path(file).name))
        state = FitParseState(
            activity_name=activity_name_input or "Workout",
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
    except Exception as err:
        logger.error("Error in parse_fit_file", exc_info=err, extra=core_logger.context(file=Path(file).name))
        raise core_exceptions.ProcessingError("Can't parse FIT file") from err
