from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones

import fitdecode
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import activities.activity_file_import.utils as activity_file_import_utils
import activities.activity_workout_steps.schema as activity_workout_steps_schema
import core.config as core_config
import core.logger as core_logger
import garmin.utils as garmin_utils
import gears.gear.crud as gears_crud
import users.users_default_gear.utils as user_default_gear_utils
import users.users_privacy_settings.models as users_privacy_settings_models


def create_activity_objects(
    sessions_records: dict,
    user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    garmin_activity_id: int | None = None,
    garminconnect_gear: dict | None = None,
    db: Session = None,
) -> list:
    try:
        timezone = core_config.settings.TZ

        # Define variables
        gear_id = None

        if garminconnect_gear:
            user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)

            if user_integrations.garminconnect_sync_gear:
                # set the gear id for the activity
                gear = gears_crud.get_gear_by_garminconnect_id_from_user_id(garminconnect_gear[0]["uuid"], user_id, db)

                # set the gear id for the activity
                if gear is not None:
                    gear_id = gear.id

        activities = []

        for session_record in sessions_records:
            # Define default values
            activity_type = 10
            activity_name = "Workout"
            pace = 0

            if session_record["session"]["activity_type"]:
                # Set the activity type based on the session record
                activity_type = activities_utils.define_activity_type(session_record["session"]["activity_type"])

                if gear_id is None:
                    gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(user_id, activity_type, db)

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
            total_timer_time, pace = calculate_pace(
                resolved_distance,
                session_record["session"]["total_timer_time"],
                session_record["session"]["activity_type"],
                session_record["split_summary"],
                session_record["lengths"],
            )

            if activity_type != 3 and activity_type != 7:
                if session_record["is_lat_lon_set"]:
                    timezone = activity_file_import_utils.resolve_timezone_from_lat_lon(
                        session_record["lat_lon_waypoints"][0]["lat"],
                        session_record["lat_lon_waypoints"][0]["lon"],
                        timezone,
                    )
                else:
                    if session_record["time_offset"]:
                        timezone = find_timezone_name(
                            session_record["time_offset"],
                            session_record["session"]["first_waypoint_time"],
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

            privacy_kwargs = activity_file_import_utils.build_activity_privacy_kwargs(user_privacy_settings)

            # Recompute avg/max HR from waypoints, excluding zeros (zero is not a
            # valid HR value — it means the sensor was disconnected). This overrides
            # the device-computed session value which may include zero-readings.
            session_avg_hr = session_record["session"]["avg_hr"]
            session_max_hr = session_record["session"]["max_hr"]
            if session_record.get("hr_waypoints"):
                recomputed_avg, recomputed_max = activities_utils.calculate_avg_and_max(
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
                vel_avg, vel_max = activities_utils.calculate_avg_and_max(
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
                cad_avg, cad_max = activities_utils.calculate_avg_and_max(
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
                computed_gain, computed_loss = activities_utils.compute_elevation_gain_and_loss(
                    elevations=session_record["ele_waypoints"],
                )
                if ele_gain is None and computed_gain:
                    ele_gain = round(computed_gain)
                if ele_loss is None and computed_loss:
                    ele_loss = round(computed_loss)

            activity = activities_schema.Activity(
                user_id=user_id,
                name=activity_name,
                distance=(round(resolved_distance) if resolved_distance else 0),
                activity_type=activity_type,
                start_time=session_record["session"]["first_waypoint_time"].strftime("%Y-%m-%dT%H:%M:%S"),
                end_time=session_record["session"]["last_waypoint_time"].strftime("%Y-%m-%dT%H:%M:%S"),
                timezone=timezone,
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
                gear_id=gear_id,
                strava_gear_id=None,
                strava_activity_id=None,
                garminconnect_activity_id=garmin_activity_id,
                garminconnect_gear_id=(garminconnect_gear[0]["uuid"] if garminconnect_gear else None),
                tracker_manufacturer=(
                    str(manufacturer)
                    if (manufacturer := session_record["file_id"].get("manufacturer")) is not None
                    else None
                ),
                tracker_model=(str(model) if (model := session_record["file_id"].get("product")) is not None else None),
                **privacy_kwargs,
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

        return activities
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in create_activity_objects: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Can't parse FIT file sessions",
        ) from err


def split_records_by_activity(parsed_data: dict) -> dict:
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
    activity_waypoints = {
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

    sessions_records = []

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

                # Use geocoding API to get city, town, and country
                location_data = activity_file_import_utils.resolve_location(
                    session["initial_latitude"], session["initial_longitude"]
                )
                if location_data:
                    parsed_session["session"]["city"] = location_data["city"]
                    parsed_session["session"]["town"] = location_data["town"]
                    parsed_session["session"]["country"] = location_data["country"]

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
    ) = parse_frame_session(frame)

    city, town, country = None, None, None
    if initial_latitude is not None and initial_longitude is not None:
        location_data = activity_file_import_utils.resolve_location(initial_latitude, initial_longitude)
        if location_data:
            city = location_data["city"]
            town = location_data["town"]
            country = location_data["country"]

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
    split_data = parse_frame_split(frame)
    state.splits.append(dict(zip(_SPLIT_KEYS, split_data, strict=False)))


def _handle_split_summary_frame(frame, state: FitParseState) -> None:
    """Parse a split_summary frame and append it to state."""
    split_type, total_timer_time = parse_frame_split_summary(frame)
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
    ) = parse_frame_record(frame)

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
        instant_speed = activities_utils.calculate_instant_speed(
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

    activities_utils.append_if_not_none(state.ele_waypoints, timestamp, elevation, "ele")
    activities_utils.append_if_not_none(state.hr_waypoints, timestamp, heart_rate, "hr")
    activities_utils.append_if_not_none(state.cad_waypoints, timestamp, cadence, "cad")
    activities_utils.append_if_not_none(state.power_waypoints, timestamp, power, "power")
    activities_utils.append_if_not_none(state.vel_waypoints, timestamp, instant_speed, "vel")
    activities_utils.append_if_not_none(state.pace_waypoints, timestamp, instant_pace, "pace")
    activities_utils.append_if_not_none(state.temp_waypoints, timestamp, temperature, "temp")

    state.prev_latitude = latitude
    state.prev_longitude = longitude
    state.last_waypoint_time = time


def _handle_monitoring_frame(frame, state: FitParseState, last_timestamp) -> None:
    """Parse a monitoring frame and extend intraday collections."""
    steps, heart_rate = parse_frame_monitoring(frame, last_timestamp)
    state.intraday_steps.extend(steps)
    state.intraday_heart_rate.extend(heart_rate)


def _dispatch_data_message(frame, state: FitParseState, last_timestamp) -> None:
    """Route a FIT data message to the appropriate handler."""
    name = frame.name
    if name == "session":
        _handle_session_frame(frame, state)
    elif name == "workout":
        state.activity_name = parse_frame_workout(frame)
    elif name == "lap":
        state.laps.append(parse_frame_lap(frame))
    elif name in {"split", "unknown_312"}:
        _handle_split_frame(frame, state)
    elif name in {"split_summary", "unknown_313"}:
        _handle_split_summary_frame(frame, state)
    elif name == "set":
        state.sets.append(parse_frame_set(frame))
    elif name == "workout_step":
        state.workout_steps.append(parse_frame_workout_step(frame))
    elif name == "exercise_title":
        state.exercises_titles.append(parse_frame_exercise_title(frame))
    elif name == "record":
        _handle_record_frame(frame, state)
    elif name == "device_settings":
        state.time_offset = interpret_time_offset(parse_frame_device_settings(frame))
    elif name == "length":
        state.lengths.append(parse_frame_length(frame))
    elif name == "file_id":
        state.file_id = parse_frame_file_id(frame)
    elif name == "monitoring":
        _handle_monitoring_frame(frame, state, last_timestamp)
    elif name == "monitoring_hr_data":
        state.resting_heart_rate = parse_frame_monitoring_hr_data(frame)


def parse_fit_file(file: str, db: Session, activity_name_input: str | None = None) -> dict:
    try:
        state = FitParseState(
            activity_name=activity_name_input or "Workout",
        )

        with open(file, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    _dispatch_data_message(frame, state, fit_data.last_timestamp)

        if state.exercises_titles:
            activity_exercise_titles_crud.create_activity_exercise_titles(state.exercises_titles, db)

        return state.to_payload()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in parse_fit_file: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Can't parse FIT file",
        ) from err


def parse_frame_session(frame):
    # Extracting coordinates
    initial_latitude, initial_longitude = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "start_position_lat"),
        get_value_from_frame(frame, "start_position_long"),
    )

    # Activity type logic
    activity_type = get_value_from_frame(frame, "sport", "Workout")
    sub_sport = get_value_from_frame(frame, "sub_sport")
    if sub_sport and sub_sport != "generic":
        if activity_type == "cycling" and sub_sport == "virtual_activity":
            activity_type = "virtual_ride"
        elif activity_type == "cycling" and sub_sport == "commuting":
            activity_type = "commuting_ride"
        elif activity_type == "cycling" and sub_sport == "mixed_surface":
            activity_type = "mixed_surface_ride"
        elif (activity_type == "generic" and sub_sport == "breathing") or activity_type == 62:
            activity_type = "hiit"
        elif activity_type == 64 and sub_sport == 85:
            activity_type = "padel"
        else:
            activity_type = sub_sport

    # Extracting time values
    start_time = get_value_from_frame(frame, "start_time")
    total_elapsed_time = get_value_from_frame(frame, "total_elapsed_time")
    total_timer_time = get_value_from_frame(frame, "total_timer_time")

    # Extracting other values
    return (
        initial_latitude,
        initial_longitude,
        activity_type,
        start_time,
        total_elapsed_time,
        total_timer_time,
        get_value_from_frame(frame, "total_calories"),
        get_value_from_frame(frame, "total_distance"),
        get_value_from_frame(frame, "avg_heart_rate"),
        get_value_from_frame(frame, "max_heart_rate"),
        get_value_from_frame(frame, "avg_cadence"),
        get_value_from_frame(frame, "max_cadence"),
        get_value_from_frame(frame, "avg_power"),
        get_value_from_frame(frame, "max_power"),
        get_value_from_frame(frame, "total_ascent"),
        get_value_from_frame(frame, "total_descent"),
        get_value_from_frame(frame, "normalized_power"),
        # Prefer the enhanced speed fields, falling back to the legacy
        # avg_speed/max_speed fields some devices write instead.
        get_value_from_frame(frame, "enhanced_avg_speed", get_value_from_frame(frame, "avg_speed")),
        get_value_from_frame(frame, "enhanced_max_speed", get_value_from_frame(frame, "max_speed")),
        get_value_from_frame(frame, "workout_feel"),
        get_value_from_frame(frame, "workout_rpe"),
        get_value_from_frame(frame, "total_cycles"),
    )


def parse_frame_workout(frame):
    # Return the extracted name
    return get_value_from_frame(frame, "wkt_name", "Workout")


def parse_frame_record(frame):
    # Extracting data using the helper function
    latitude = get_value_from_frame(frame, "position_lat")
    longitude = get_value_from_frame(frame, "position_long")
    elevation = get_value_from_frame(frame, "enhanced_altitude")
    time = get_value_from_frame(frame, "timestamp")
    heart_rate = get_value_from_frame(frame, "heart_rate")
    cadence = get_value_from_frame(frame, "cadence")
    power = get_value_from_frame(frame, "power")
    temperature = get_value_from_frame(frame, "temperature")

    latitude, longitude = convert_coordinates_to_degrees(latitude, longitude)

    # Return all extracted values
    return latitude, longitude, elevation, time, heart_rate, cadence, power, temperature


def parse_frame_lap(frame):
    keys = [
        "start_time",
        "start_position_lat",
        "start_position_long",
        "end_position_lat",
        "end_position_long",
        "total_elapsed_time",
        "total_timer_time",
        "total_distance",
        "total_cycles",
        "total_calories",
        "avg_heart_rate",
        "max_heart_rate",
        "avg_cadence",
        "max_cadence",
        "avg_power",
        "max_power",
        "total_ascent",
        "total_descent",
        "intensity",
        "lap_trigger",
        "sport",
        "sub_sport",
        "normalized_power",
        "total_work",
        "avg_vertical_oscillation",
        "avg_stance_time",
        "avg_fractional_cadence",
        "max_fractional_cadence",
        "enhanced_avg_speed",
        "enhanced_max_speed",
        "enhanced_min_altitude",
        "enhanced_max_altitude",
        "avg_vertical_ratio",
        "avg_step_length",
    ]

    lap_data = tuple(get_value_from_frame(frame, key) for key in keys)
    lap_dict = dict(zip(keys, lap_data, strict=False))

    (
        lap_dict["start_position_lat"],
        lap_dict["start_position_long"],
    ) = convert_coordinates_to_degrees(
        lap_dict["start_position_lat"],
        lap_dict["start_position_long"],
    )
    lap_dict["end_position_lat"], lap_dict["end_position_long"] = convert_coordinates_to_degrees(
        lap_dict["end_position_lat"],
        lap_dict["end_position_long"],
    )

    if lap_dict["enhanced_avg_speed"]:
        lap_dict["enhanced_avg_pace"] = 1 / lap_dict["enhanced_avg_speed"]

    if lap_dict["enhanced_max_speed"]:
        lap_dict["enhanced_max_pace"] = 1 / lap_dict["enhanced_max_speed"]

    return lap_dict


def parse_frame_split(frame):
    # Define a list of keys and their default values
    keys_defaults = [
        ("split_type", 0),
        ("total_elapsed_time", 1),
        ("total_timer_time", 2),
        ("total_distance", 3),
        ("avg_speed", 4),
        ("start_time", 9),
        ("total_ascent", 13),
        ("total_descent", 14),
        ("start_position_lat", 21),
        ("start_position_long", 22),
        ("end_position_lat", 23),
        ("end_position_long", 24),
        ("max_speed", 25),
        ("end_time", 27),
        ("total_calories", 28),
        ("start_elevation", 74),
    ]

    # Extract values using the keys and defaults
    values = [get_value_from_frame(frame, key, get_value_from_frame(frame, default)) for key, default in keys_defaults]

    return tuple(values)


def parse_frame_split_summary(frame):
    # split type
    split_type = get_value_from_frame(frame, "split_type")
    if split_type is None:
        split_type = get_value_from_frame(frame, 0)
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")
    if total_timer_time is None:
        total_timer_time = get_value_from_frame(frame, 4)
        if total_timer_time is not None:
            total_timer_time = total_timer_time / 1000

    return split_type, total_timer_time


def parse_frame_set(frame):
    keys_value = [
        "duration",
        "repetitions",
        "weight",
        "set_type",
        "start_time",
    ]

    keys_raw = [
        "category",
        "category_subtype",
    ]

    set_data = [get_value_from_frame(frame, key) for key in keys_value]
    set_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    # Adjust category based on category_subtype
    if set_data[5] is None:
        set_data[5] = 0 if set_data[6] is not None else None

    return list(set_data)


def parse_frame_workout_step(frame):
    keys_value = [
        "message_index",
        "duration_type",
        "duration_value",
        "target_type",
        "target_value",
        "intensity",
        "notes",
        "exercise_weight",
        "weight_display_unit",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    workout_set_data = [get_value_from_frame(frame, key) for key in keys_value]
    workout_set_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    secondary_target_value = None

    if workout_set_data[3] == "swim_stroke":
        if isinstance(workout_set_data[4], str):
            secondary_target_value = workout_set_data[4]
            workout_set_data[4] = None
        elif isinstance(workout_set_data[4], int) and workout_set_data[4] == 255:
            secondary_target_value = "any stroke"
            workout_set_data[4] = None

    if workout_set_data[5] == 7:
        workout_set_data[5] = "active"

    if workout_set_data[9] is None:
        workout_set_data[9] = 0 if workout_set_data[10] is not None else None

    return activity_workout_steps_schema.ActivityWorkoutSteps(
        message_index=workout_set_data[0] if workout_set_data[0] else 0,
        duration_type=workout_set_data[1],
        duration_value=workout_set_data[2],
        target_type=workout_set_data[3],
        target_value=workout_set_data[4] if workout_set_data[4] else None,
        intensity=workout_set_data[5] if isinstance(workout_set_data[5], str) else None,
        notes=workout_set_data[6],
        exercise_category=workout_set_data[9],
        exercise_name=workout_set_data[10] if workout_set_data[10] else None,
        exercise_weight=workout_set_data[7],
        weight_display_unit=workout_set_data[8],
        secondary_target_value=secondary_target_value,
    )


def parse_frame_exercise_title(frame):
    keys_value = [
        "wkt_step_name",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    exercise_title_data = [get_value_from_frame(frame, key) for key in keys_value]
    exercise_title_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    return activity_exercise_titles_schema.ActivityExerciseTitles(
        exercise_category=exercise_title_data[1] if exercise_title_data[1] else 0,
        exercise_name=exercise_title_data[2] if exercise_title_data[2] else 0,
        wkt_step_name=str(exercise_title_data[0]),
    )


def parse_frame_device_settings(frame):
    return get_value_from_frame(frame, "time_offset")


def parse_frame_length(frame):
    return {
        "message_index": get_value_from_frame(frame, "message_index"),
        "start_time": get_value_from_frame(frame, "start_time"),
        "total_elapsed_time": get_value_from_frame(frame, "total_elapsed_time"),
        "total_timer_time": get_value_from_frame(frame, "total_timer_time"),
        "total_strokes": get_value_from_frame(frame, "total_strokes"),
        "avg_speed": get_value_from_frame(frame, "avg_speed"),
        "swim_stroke": get_value_from_frame(frame, "swim_stroke"),
        "avg_swimming_cadence": get_value_from_frame(frame, "avg_swimming_cadence"),
        "length_type": get_value_from_frame(frame, "length_type"),
    }


def parse_frame_file_id(frame):
    return {
        "type": get_value_from_frame(frame, "type"),
        "manufacturer": get_value_from_frame(frame, "manufacturer"),
        "product": get_value_from_frame(frame, "product"),
        "serial_number": get_value_from_frame(frame, "serial_number"),
        "time_created": get_value_from_frame(frame, "time_created"),
    }


def parse_frame_monitoring(frame, last_timestamp):
    steps = []
    heart_rate = []

    data = {}
    for frame_field in frame.fields:
        data.update({frame_field.name: frame_field.value})
        for sf in getattr(frame_field.field, "subfields", []) or []:
            data.update({sf.name: sf.render(frame_field.raw_value)})

    # Reconstruct timestamp with timestamp_16.
    current_timestamp = None
    if data.get("timestamp_16") is not None:
        current_timestamp = (last_timestamp & 0xFFFF0000) | data["timestamp_16"]
        if current_timestamp < last_timestamp:
            current_timestamp += 0x10000
    else:
        current_timestamp = last_timestamp

    timestamp = datetime.fromtimestamp(
        current_timestamp + fitdecode.FIT_UTC_REFERENCE,
        tz=UTC,
    )

    if data.get("steps"):
        steps.append(
            {
                "steps": data.get("steps"),
                "active_time": data.get("active_time"),
                "active_calories": data.get("active_calories"),
                "current_activity_type_intensity": data.get("current_activity_type_intensity"),
                "activity_type": data.get("activity_type"),
                "intensity": data.get("intensity"),
                "distance": data.get("distance"),
                "duration_min": data.get("duration_min"),
                "timestamp": timestamp,
            }
        )

    if data.get("heart_rate"):
        heart_rate.append(
            {
                "heart_rate": data.get("heart_rate"),
                "timestamp": timestamp,
            }
        )

    return steps, heart_rate


def parse_frame_monitoring_hr_data(frame):
    return {
        "timestamp": get_value_from_frame(frame, "timestamp"),
        "resting_heart_rate": get_value_from_frame(frame, "resting_heart_rate"),
        "current_day_resting_heart_rate": get_value_from_frame(frame, "current_day_resting_heart_rate"),
    }


def interpret_time_offset(raw_offset):
    # Check for two's complement representation (values > 2^31)
    if raw_offset != 0 and raw_offset is not None and raw_offset > 2**31 - 1:
        return raw_offset - 2**32
    return raw_offset


def get_value_from_frame(frame, key, default=None):
    try:
        value = frame.get_value(key)
        return value if value else default
    except KeyError:
        return default


def get_raw_value_from_frame(frame, key, default=None):
    try:
        raw_value = frame.get_raw_value(key)
        return raw_value if raw_value else default
    except KeyError:
        return default


def convert_coordinates_to_degrees(latitude, longitude):
    # Convert FIT coordinates to degrees if available
    if latitude is not None and longitude is not None:
        latitude = latitude * (180 / 2**31)
        longitude = longitude * (180 / 2**31)

    return latitude, longitude


def append_if_not_none(waypoint_list, time, value, key):
    if value is not None:
        waypoint_list.append({"time": time, key: value})


def calculate_pace(distance, total_timer_time, activity_type, split_summary, lengths):
    if distance:
        if activity_type != "lap_swimming" or (activity_type == "lap_swimming" and not split_summary and not lengths):
            return total_timer_time, total_timer_time / distance
        if activity_type == "lap_swimming" and lengths:
            # Swimming pace calculation based on lengths
            time_active = 0
            for length in lengths:
                if length["length_type"] == "active":
                    time_active += length["total_timer_time"]

            return time_active, time_active / distance
        # Swimming pace calculation based on split summary
        time_active = 0
        for split in split_summary:
            if split["split_type"] != 4:
                time_active += split["total_timer_time"]

        return time_active, time_active / distance
    return total_timer_time, 0


def find_timezone_name(offset_seconds, reference_date):
    for tz_name in available_timezones():
        tz = ZoneInfo(tz_name)

        # Get the UTC offset of the candidate timezone for
        # the reference date (DST-aware).
        utc_offset = reference_date.astimezone(tz).utcoffset()
        if utc_offset is None:  # Skip invalid timezones
            continue

        if utc_offset.total_seconds() == offset_seconds:
            return tz_name

    return None
