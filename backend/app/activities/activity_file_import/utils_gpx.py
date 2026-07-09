"""Utilities for parsing GPX files into activity data."""

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import TypedDict

import gpxpy
import gpxpy.gpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import activities.activity_file_import.utils as activity_file_import_utils
import core.config as core_config
import core.logger as core_logger
import core.timezone as core_timezone
import users.users_default_gear.utils as user_default_gear_utils
import users.users_privacy_settings.models as users_privacy_settings_models

# Re-export for backwards compatibility (migration_3.py calls
# gpx_utils.generate_activity_laps directly).
from activities.activity_file_import.utils import (
    LapMetrics,
    generate_activity_laps,
)

# Activity type IDs that do not use GPS-based timezone
# detection (e.g. indoor/pool activities)
_ACTIVITY_TYPE_POOL_SWIM = 3
_ACTIVITY_TYPE_TREADMILL = 7

# Inclusive plausible elevation range in meters. Values outside this range
# (or non-finite) are dropped to guard against sentinel/garbage readings.
_ELEVATION_MIN = -9999.99
_ELEVATION_MAX = 9999.99


@dataclass
class ParseState:
    """
    Mutable state accumulated while parsing a GPX file.

    Attributes are grouped into activity metadata, aggregate metrics,
    waypoint streams, segment-local cursors, and stream-presence flags.
    """

    timezone: str
    activity_name: str = "Workout"
    activity_type: str | int = "Workout"
    activity_description: str | None = None
    calories: int | None = None
    distance: float = 0.0
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_cadence: float | None = None
    max_cadence: float | None = None
    avg_power: float | None = None
    max_power: float | None = None
    normalized_power: float | None = None
    avg_speed: float | None = None
    max_speed: float | None = None
    ele_gain: float | None = None
    ele_loss: float | None = None
    pace: float = 0
    first_waypoint_time: datetime | None = None
    last_waypoint_time: datetime | None = None
    location_resolved: bool = False
    gear_id: int | None = None
    city: str | None = None
    town: str | None = None
    country: str | None = None
    lat_lon_waypoints: list[dict] = field(default_factory=list)
    ele_waypoints: list[dict] = field(default_factory=list)
    hr_waypoints: list[dict] = field(default_factory=list)
    cad_waypoints: list[dict] = field(default_factory=list)
    power_waypoints: list[dict] = field(default_factory=list)
    vel_waypoints: list[dict] = field(default_factory=list)
    pace_waypoints: list[dict] = field(default_factory=list)
    prev_latitude: float | None = None
    prev_longitude: float | None = None
    prev_waypoint_time: datetime | None = None
    lat_lon_segments: list[list[dict]] = field(default_factory=list)
    is_lat_lon_set: bool = False
    is_elevation_set: bool = False
    is_power_set: bool = False
    is_heart_rate_set: bool = False
    is_cadence_set: bool = False
    is_velocity_set: bool = False

    def reset_segment(self) -> None:
        """Clear cursors that must not carry across GPX segments."""
        self.prev_latitude = None
        self.prev_longitude = None
        self.prev_waypoint_time = None


class ParsedGpxData(TypedDict):
    """
    Typed dictionary for parsed GPX file output.

    Attributes:
        activity: Populated Activity schema.
        is_elevation_set: Whether elevation data exists.
        ele_waypoints: List of elevation waypoints.
        is_power_set: Whether power data exists.
        power_waypoints: List of power waypoints.
        is_heart_rate_set: Whether HR data exists.
        hr_waypoints: List of heart rate waypoints.
        is_velocity_set: Whether velocity data exists.
        vel_waypoints: List of velocity waypoints.
        pace_waypoints: List of pace waypoints.
        is_cadence_set: Whether cadence data exists.
        cad_waypoints: List of cadence waypoints.
        is_lat_lon_set: Whether GPS data exists.
        lat_lon_waypoints: List of GPS waypoints.
        laps: List of computed lap metrics.
    """

    activity: activities_schema.Activity
    is_elevation_set: bool
    ele_waypoints: list[dict]
    is_power_set: bool
    power_waypoints: list[dict]
    is_heart_rate_set: bool
    hr_waypoints: list[dict]
    is_velocity_set: bool
    vel_waypoints: list[dict]
    pace_waypoints: list[dict]
    is_cadence_set: bool
    cad_waypoints: list[dict]
    is_lat_lon_set: bool
    lat_lon_waypoints: list[dict]
    laps: list[LapMetrics]


def _extension_local_name(tag: str) -> str:
    """
    Return a lowercase XML local name from a namespaced tag.

    Args:
        tag: ElementTree tag in plain, prefixed, or Clark notation.

    Returns:
        Lowercase local tag name.
    """
    return tag.rsplit("}", maxsplit=1)[-1].rsplit(":", maxsplit=1)[-1].lower()


def _safe_optional_int(text: str | None) -> int | None:
    """
    Convert extension text to an integer if possible.

    Args:
        text: Raw extension text.

    Returns:
        Parsed integer, or None when the text is empty or invalid.
    """
    if text is None:
        return None

    try:
        return int(float(text.strip()))
    except ValueError:
        return None


def _safe_int(text: str | None) -> int:
    """
    Convert extension text to an integer if possible.

    Args:
        text: Raw extension text.

    Returns:
        Parsed integer, or 0 when the text is empty or invalid.
    """
    value = _safe_optional_int(text)
    return value if value is not None else 0


def _sanitize_elevation(elevation: float | None) -> float | None:
    """
    Return elevation only when it is finite and plausible.

    Args:
        elevation: Raw elevation value from a GPX trackpoint.

    Returns:
        Elevation in meters, or None when missing or invalid.
    """
    if elevation is None or not isfinite(elevation):
        return None

    if _ELEVATION_MIN <= elevation <= _ELEVATION_MAX:
        return elevation

    return None


def _extract_extension_data(
    point: gpxpy.gpx.GPXTrackPoint,
) -> tuple[int, int, int]:
    """
    Extract HR, cadence, and power from extensions.

    Args:
        point: A gpxpy trackpoint with optional extension elements.

    Returns:
        Tuple of (heart_rate, cadence, power) as ints.
    """
    heart_rate: int = 0
    cadence: int = 0
    power: int = 0

    if not point.extensions:
        return heart_rate, cadence, power

    for extension in point.extensions:
        for element in extension.iter():
            tag = _extension_local_name(element.tag)
            value = _safe_int(element.text)

            if tag in ("hr", "heartrate", "heart_rate"):
                heart_rate = value
            elif tag in ("cad", "cadence"):
                cadence = value
            elif tag in ("power", "PowerInWatts"):
                power = value

    return heart_rate, cadence, power


def _extract_track_calories(
    track: gpxpy.gpx.GPXTrack,
) -> int | None:
    """
    Extract total calories from track-level extensions.

    Sums every ``Calories`` element found beneath the track's extension
    blocks so files with multiple extension containers aggregate correctly.

    Args:
        track: GPX track with optional extension elements.

    Returns:
        Calories as an integer, or None when absent or invalid.
    """
    if not track.extensions:
        return None

    total: int | None = None
    for extension in track.extensions:
        for element in extension.iter():
            if _extension_local_name(element.tag) != "calories":
                continue
            value = _safe_optional_int(element.text)
            if value is None:
                continue
            total = (total or 0) + value

    return total


def _init_parsing_state(
    activity_name_input: str | None,
    timezone: str,
) -> ParseState:
    """
    Initialize mutable state for a GPX parse run.

    Args:
        activity_name_input: Optional user-supplied name.
        timezone: Default timezone string.

    Returns:
        ParseState with all tracking fields at default values.
    """
    return ParseState(
        timezone=timezone,
        activity_name=activity_name_input or "Workout",
    )


def _process_track_metadata(
    track: gpxpy.gpx.GPXTrack,
    gpx: gpxpy.gpx.GPX,
    state: ParseState,
) -> None:
    """
    Extract track-level metadata into parsing state.

    Args:
        track: GPX track object.
        gpx: Root GPX object.
        state: Mutable parse state.

    Returns:
        None
    """
    state.activity_name = track.name or gpx.name or "Workout"
    state.activity_description = track.description or gpx.description or None
    state.activity_type = track.type or "Workout"

    calories = _extract_track_calories(track)
    if calories is not None:
        state.calories = (state.calories or 0) + calories


def _process_trackpoint(
    point: gpxpy.gpx.GPXTrackPoint,
    state: ParseState,
) -> None:
    """
    Process a single trackpoint and update parsing state.

    Args:
        point: GPX trackpoint to process.
        state: Mutable parse state.

    Returns:
        None
    """
    latitude = point.latitude
    longitude = point.longitude
    elevation = _sanitize_elevation(point.elevation)
    time = point.time

    # Skip trackpoints without time (OsmAnd exports)
    if time is None:
        return

    if elevation is not None:
        state.is_elevation_set = True

    if state.first_waypoint_time is None:
        state.first_waypoint_time = time

    if not state.location_resolved:
        location_data = activity_file_import_utils.resolve_location(
            latitude,
            longitude,
        )
        if location_data:
            state.city = location_data["city"]
            state.town = location_data["town"]
            state.country = location_data["country"]
            state.location_resolved = True

    heart_rate, cadence, raw_power = _extract_extension_data(point)
    power: int | None = raw_power

    if heart_rate != 0:
        state.is_heart_rate_set = True
    if cadence != 0:
        state.is_cadence_set = True
    if raw_power != 0:
        state.is_power_set = True
    else:
        power = None

    instant_speed = activities_utils.calculate_instant_speed(
        state.prev_waypoint_time,
        time,
        latitude,
        longitude,
        state.prev_latitude,
        state.prev_longitude,
    )

    instant_pace: float = 0
    if instant_speed > 0:
        instant_pace = 1 / instant_speed
        state.is_velocity_set = True

    timestamp = core_timezone.format_utc(time)

    if latitude is not None and longitude is not None:
        state.lat_lon_waypoints.append(
            {
                "time": timestamp,
                "lat": latitude,
                "lon": longitude,
            }
        )
        state.is_lat_lon_set = True

    activities_utils.append_if_not_none(
        state.ele_waypoints,
        timestamp,
        elevation,
        "ele",
    )
    activities_utils.append_if_not_none(
        state.hr_waypoints,
        timestamp,
        heart_rate,
        "hr",
    )
    activities_utils.append_if_not_none(
        state.cad_waypoints,
        timestamp,
        cadence,
        "cad",
    )
    activities_utils.append_if_not_none(
        state.power_waypoints,
        timestamp,
        power,
        "power",
    )
    activities_utils.append_if_not_none(
        state.vel_waypoints,
        timestamp,
        instant_speed,
        "vel",
    )
    activities_utils.append_if_not_none(
        state.pace_waypoints,
        timestamp,
        instant_pace,
        "pace",
    )

    state.prev_latitude = latitude
    state.prev_longitude = longitude
    state.prev_waypoint_time = time
    state.last_waypoint_time = time


def _compute_derived_metrics(
    state: ParseState,
    user_id: int,
    db: Session,
) -> None:
    """
    Compute derived activity metrics and update state.

    Args:
        state: Mutable parse state.
        user_id: ID of the user.
        db: SQLAlchemy database session.

    Returns:
        None
    """
    if state.ele_waypoints:
        gain, loss = activities_utils.compute_elevation_gain_and_loss(
            elevations=state.ele_waypoints,
        )
        state.ele_gain = gain
        state.ele_loss = loss

    state.pace = activities_utils.calculate_pace(
        state.distance,
        state.first_waypoint_time,
        state.last_waypoint_time,
    )

    state.activity_type = activities_utils.define_activity_type(
        str(state.activity_type),
    )

    state.gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(
        user_id,
        state.activity_type,
        db,
    )

    if state.hr_waypoints:
        state.avg_hr, state.max_hr = activities_utils.calculate_avg_and_max(
            state.hr_waypoints,
            "hr",
        )

    if state.cad_waypoints:
        state.avg_cadence, state.max_cadence = activities_utils.calculate_avg_and_max(
            state.cad_waypoints,
            "cad",
        )

    if state.vel_waypoints:
        state.avg_speed, state.max_speed = activities_utils.calculate_avg_and_max(
            state.vel_waypoints,
            "vel",
        )

    if state.power_waypoints:
        (
            state.avg_power,
            state.max_power,
            state.normalized_power,
        ) = activity_file_import_utils.calculate_power_metrics(state.power_waypoints)

    if (
        state.activity_type
        not in (
            _ACTIVITY_TYPE_POOL_SWIM,
            _ACTIVITY_TYPE_TREADMILL,
        )
        and state.is_lat_lon_set
    ):
        state.timezone = activity_file_import_utils.resolve_timezone_from_lat_lon(
            state.lat_lon_waypoints[0]["lat"],
            state.lat_lon_waypoints[0]["lon"],
            state.timezone,
        )


def _build_activity_schema(
    state: ParseState,
    user_id: int,
    user_privacy_settings: (users_privacy_settings_models.UsersPrivacySettings),
) -> activities_schema.Activity:
    """
    Build an Activity Pydantic schema from parsed state.

    Args:
        state: Parsed GPX state.
        user_id: ID of the user.
        user_privacy_settings: ORM privacy settings object.

    Returns:
        Populated Activity schema instance.
    """
    privacy_kwargs = activity_file_import_utils.build_activity_privacy_kwargs(user_privacy_settings)
    if state.first_waypoint_time is None or state.last_waypoint_time is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Missing waypoint timestamps in GPX parse state",
        )
    elapsed = (state.last_waypoint_time - state.first_waypoint_time).total_seconds()
    return activities_schema.Activity(
        user_id=user_id,
        name=state.activity_name,
        description=state.activity_description,
        distance=round(state.distance) if state.distance else 0,
        activity_type=int(state.activity_type),
        start_time=core_timezone.format_utc(state.first_waypoint_time),
        end_time=core_timezone.format_utc(state.last_waypoint_time),
        timezone=state.timezone,
        total_elapsed_time=elapsed,
        total_timer_time=elapsed,
        city=state.city,
        town=state.town,
        country=state.country,
        elevation_gain=(round(state.ele_gain) if state.ele_gain else None),
        elevation_loss=(round(state.ele_loss) if state.ele_loss else None),
        pace=state.pace,
        average_speed=state.avg_speed,
        max_speed=state.max_speed,
        average_power=(round(state.avg_power) if state.avg_power else None),
        max_power=round(state.max_power) if state.max_power else None,
        normalized_power=(round(state.normalized_power) if state.normalized_power else None),
        average_hr=round(state.avg_hr) if state.avg_hr else None,
        max_hr=round(state.max_hr) if state.max_hr else None,
        average_cad=(round(state.avg_cadence) if state.avg_cadence else None),
        max_cad=(round(state.max_cadence) if state.max_cadence else None),
        calories=state.calories,
        gear_id=state.gear_id,
        strava_gear_id=None,
        strava_activity_id=None,
        garminconnect_activity_id=None,
        garminconnect_gear_id=None,
        **privacy_kwargs,
    )


def parse_gpx_file(
    file: str,
    user_id: int,
    user_privacy_settings: (users_privacy_settings_models.UsersPrivacySettings),
    db: Session,
    activity_name_input: str | None = None,
) -> ParsedGpxData:
    """
    Parse a GPX file into structured activity data.

    Args:
        file: Path to the GPX file on disk.
        user_id: ID of the user uploading the file.
        user_privacy_settings: ORM privacy settings for the user.
        db: SQLAlchemy database session.
        activity_name_input: Optional override for the activity name.

    Returns:
        ParsedGpxData with Activity schema, waypoint
        arrays, lap data, and boolean stream flags.

    Raises:
        HTTPException: 400 if the GPX has no tracks, no segments, or no valid
            timed trackpoints.
        HTTPException: 500 if the file cannot be read.
    """
    try:
        state = _init_parsing_state(
            activity_name_input,
            core_config.settings.TZ,
        )

        with Path(file).open("r", encoding="utf-8") as gpx_file:
            gpx = gpxpy.parse(gpx_file)

            if not gpx.tracks:
                raise HTTPException(
                    status_code=(status.HTTP_400_BAD_REQUEST),
                    detail=("Invalid GPX file - no tracks found in the GPX file"),
                )

            for track in gpx.tracks:
                _process_track_metadata(track, gpx, state)

                if not track.segments:
                    raise HTTPException(
                        status_code=(status.HTTP_400_BAD_REQUEST),
                        detail=("Invalid GPX file - no segments found in the GPX file"),
                    )

                for segment in track.segments:
                    state.reset_segment()
                    segment_start = len(state.lat_lon_waypoints)

                    for point in segment.points:
                        _process_trackpoint(point, state)

                    segment_waypoints = state.lat_lon_waypoints[segment_start:]
                    if len(segment_waypoints) >= 2:
                        state.lat_lon_segments.append(segment_waypoints)

        if state.first_waypoint_time is None or state.last_waypoint_time is None:
            raise HTTPException(
                status_code=(status.HTTP_400_BAD_REQUEST),
                detail=("Invalid GPX file - no trackpoints with valid time data found"),
            )

        if not state.lat_lon_segments:
            raise HTTPException(
                status_code=(status.HTTP_400_BAD_REQUEST),
                detail=("Invalid GPX file - no valid segments with at least two timed GPS trackpoints found"),
            )

        # Sum distance per segment (not across the full flat waypoint list) so
        # that gaps between segments are never counted as travelled distance.
        state.distance = sum(
            activity_file_import_utils.compute_distance_from_waypoints(segment_waypoints)
            for segment_waypoints in state.lat_lon_segments
        )

        _compute_derived_metrics(state, user_id, db)

        activity = _build_activity_schema(state, user_id, user_privacy_settings)

        laps = []
        for segment_waypoints in state.lat_lon_segments:
            laps.extend(
                generate_activity_laps(
                    segment_waypoints,
                    state.ele_waypoints,
                    state.power_waypoints,
                    state.hr_waypoints,
                    state.cad_waypoints,
                    state.vel_waypoints,
                )
            )

        return ParsedGpxData(
            activity=activity,
            is_elevation_set=bool(state.ele_waypoints),
            ele_waypoints=state.ele_waypoints,
            is_power_set=bool(state.power_waypoints),
            power_waypoints=state.power_waypoints,
            is_heart_rate_set=bool(state.hr_waypoints),
            hr_waypoints=state.hr_waypoints,
            is_velocity_set=bool(state.vel_waypoints),
            vel_waypoints=state.vel_waypoints,
            pace_waypoints=state.pace_waypoints,
            is_cadence_set=bool(state.cad_waypoints),
            cad_waypoints=state.cad_waypoints,
            is_lat_lon_set=bool(state.lat_lon_waypoints),
            lat_lon_waypoints=state.lat_lon_waypoints,
            laps=laps,
        )

    except HTTPException as http_err:
        raise http_err
    except (
        gpxpy.gpx.GPXException,
        OSError,
        ValueError,
    ) as err:
        core_logger.print_to_log(
            f"Error in parse_gpx_file - {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail="Failed to parse GPX file",
        ) from err
