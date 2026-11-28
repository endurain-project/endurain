"""Strava activity sync: fetch a window, parse each activity with its streams and laps, and store it."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from sqlalchemy.orm import Session
from stravalib.client import Client
from stravalib.model import SummaryActivity

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.computation as activities_computation
import modules.gears.gear.integration_service as gears_integration
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users.integration_service as users_integration
import modules.users.users_default_gear.integration_service as users_default_gear_integration
import modules.users.users_integrations.schema as user_integrations_schema
import modules.users.users_privacy_settings.integration_service as users_privacy_settings_integration
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema

logger = core_logger.get_logger(__name__)

#: Strava's stream times are seconds from the activity start; the shared pause rule reads datetimes.
_STREAM_ORIGIN = datetime.fromtimestamp(0, UTC)

#: One sample of a stream: its ``time`` in seconds and the stream's own values, such as ``lat`` and ``lon``.
type StravaWaypoint = dict[str, float]

#: One stream of an activity: whether it is stored, its stream type and its waypoints.
type StravaStreamEntry = tuple[bool, int, list[StravaWaypoint]]

#: Each stream's waypoints followed by whether Strava sent it: lat/lon, elevation, heart rate, cadence, power and
#: velocity.
type StravaStreams = tuple[
    list[StravaWaypoint],
    bool,
    list[StravaWaypoint],
    bool,
    list[StravaWaypoint],
    bool,
    list[StravaWaypoint],
    bool,
    list[StravaWaypoint],
    bool,
    list[StravaWaypoint],
    bool,
]


class StravaLap(TypedDict):
    """A Strava lap converted to the fields a stored lap has.

    Attributes:
        start_time: When the lap started, in local time, as ``YYYY-MM-DDTHH:MM:SS``.
        start_position_lat: Latitude of the lap's first waypoint.
        start_position_long: Longitude of the lap's first waypoint.
        end_position_lat: Latitude of the lap's last waypoint.
        end_position_long: Longitude of the lap's last waypoint.
        total_elapsed_time: Elapsed time, in seconds.
        total_timer_time: Moving time, in seconds.
        total_distance: Distance, in meters.
        avg_heart_rate: Average heart rate.
        max_heart_rate: Maximum heart rate.
        avg_cadence: Average cadence, from the lap's cadence stream.
        max_cadence: Maximum cadence, from the lap's cadence stream.
        avg_power: Average power, from the lap's power stream.
        max_power: Maximum power, from the lap's power stream.
        total_ascent: Elevation gain, in meters, from the lap's elevation stream.
        total_descent: Elevation loss, in meters, from the lap's elevation stream.
        normalized_power: Normalized power, from the lap's power stream.
        enhanced_avg_pace: Average pace, in seconds per meter.
        enhanced_avg_speed: Average speed, in meters per second.
        enhanced_max_pace: Pace at the maximum speed, in seconds per meter.
        enhanced_max_speed: Maximum speed, in meters per second.
    """

    start_time: str
    start_position_lat: float | None
    start_position_long: float | None
    end_position_lat: float | None
    end_position_long: float | None
    total_elapsed_time: int | None
    total_timer_time: int | None
    total_distance: float | None
    avg_heart_rate: int | None
    max_heart_rate: int | None
    avg_cadence: int | None
    max_cadence: int | None
    avg_power: int | None
    max_power: int | None
    total_ascent: int | None
    total_descent: int | None
    normalized_power: int | None
    enhanced_avg_pace: float | None
    enhanced_avg_speed: float | None
    enhanced_max_pace: float | None
    enhanced_max_speed: float | None


class ParsedStravaActivity(TypedDict):
    """A Strava activity converted for storage.

    Attributes:
        activity_to_store: The activity to store.
        stream_data: Its streams.
        laps: Its laps, or ``None`` when Strava has none for it.
    """

    activity_to_store: activity_contracts.ActivityCore
    stream_data: list[StravaStreamEntry]
    laps: list[StravaLap] | None


def fetch_and_process_activities_by_dates(
    strava_client: Client,
    start_date: datetime,
    end_date: datetime,
    user_id: uuid.UUID,
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch a user's Strava activities in a window and store the new ones.

    Runs on a worker thread. The Strava round trips happen with no database
    session open; each activity then opens a short session of its own for the
    duplicate check, the lookups and the store.

    Args:
        strava_client: A client authenticated as the user.
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user the activities belong to.
        user_integrations: The user's integration settings.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        The activities stored from the window, or ``None`` when Strava returned nothing or the user is rate
        limited.

    Raises:
        DomainError: When Strava rejects the request, or the user or their privacy settings are missing.
        Exception: The first failure of an activity, once the rest of the window was processed.
    """
    client_id = strava_client_service.get_client_id(user_integrations)
    strava_client_service.raise_if_rate_limit_active(client_id, user_id, rate_limits)

    try:
        strava_activities = strava_client_service.call_strava(
            lambda client: list(client.get_activities(after=start_date, before=end_date)),
            strava_client,
            user_id,
            user_integrations,
            rate_limits,
        )
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        strava_client_service.raise_if_rate_limited(err, client_id, rate_limits)
        logger.warning("Error fetching Strava activities", extra=core_logger.context(user_id=user_id), exc_info=err)
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava activities") from err

    if not strava_activities:
        logger.debug(
            "No new Strava activities found", extra=core_logger.context(user_id=user_id, start_date=start_date)
        )
        return None

    with core_database.SessionLocal() as db:
        user = users_integration.get_user(user_id, db)
        if user is None:
            raise core_exceptions.NotFoundError("User not found")
        user_privacy_settings = users_privacy_settings_integration.get_privacy_settings(user.id, db)
        if user_privacy_settings is None:
            raise core_exceptions.NotFoundError("User privacy settings not found")
    # Fallback for activities with no GPS track (indoor rides, treadmill runs): prefer
    # the athlete's own timezone over the server's, which is meaningless on another continent.
    timezone = user.timezone or core_config.settings.TZ

    processed = activity_ingestion_integration.run_provider_window(
        strava_activities,
        lambda activity: process_activity(
            activity, user_id, user_privacy_settings, timezone, strava_client, user_integrations, rate_limits
        ),
        provider=strava_constants.PROVIDER_NAME,
        user_id=user_id,
        describe=lambda activity: {"strava_activity_id": activity.id},
        propagate=(core_exceptions.TooManyRequestsError, strava_client_service.StravaTokenRejectedError),
    )
    # An activity that was already stored is processed as None.
    return [stored for stored in processed if stored is not None]


def _strava_activity_id(activity: SummaryActivity, user_id: uuid.UUID) -> int:
    """Return a Strava activity's id.

    stravalib types the id as optional; without it the activity can be neither fetched nor deduplicated.

    Args:
        activity: The Strava summary activity.
        user_id: The user the activity belongs to, for the log.

    Returns:
        The activity's Strava id.

    Raises:
        DependencyFailedError: When Strava sent the activity without an id.
    """
    if activity.id is None:
        logger.warning("Strava activity has no id, skipping", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.DependencyFailedError("Strava activity has no id")
    return activity.id


def _pause_threshold(waypoints: list[StravaWaypoint]) -> float:
    """Return the gap in seconds above which a gap between a stream's samples is a pause.

    Args:
        waypoints: The whole stream, in recording order.

    Returns:
        The shared pause threshold for the stream's sample times.
    """
    return activities_computation.pause_threshold_seconds(
        [_STREAM_ORIGIN + timedelta(seconds=point["time"]) for point in waypoints]
    )


def _mean_without_zeros(waypoints: list[StravaWaypoint], key: str, max_gap: float) -> float | None:
    """Return the time-weighted mean of a stream's samples, a zero counting as no reading.

    Args:
        waypoints: The samples to average.
        key: The waypoint key holding the value.
        max_gap: The pause threshold in seconds.

    Returns:
        The mean, or ``None`` when every sample is zero or there are none.
    """
    return activities_computation.time_weighted_mean(
        [point["time"] for point in waypoints],
        [point[key] if point[key] != 0 else None for point in waypoints],
        max_gap,
    )


def _normalized_power(waypoints: list[StravaWaypoint], max_gap: float) -> float | None:
    """Return the normalized power of a power stream.

    Args:
        waypoints: The power samples.
        max_gap: The pause threshold in seconds.

    Returns:
        The normalized power in watts, or ``None`` under 30 s of power.
    """
    return activities_computation.normalized_power(
        [point["time"] for point in waypoints], [point["power"] for point in waypoints], max_gap
    )


def parse_activity(
    activity: SummaryActivity,
    user_id: uuid.UUID,
    user_privacy_settings: users_privacy_settings_schema.UserPrivacySettingsRead,
    timezone: str,
    strava_client: Client,
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> ParsedStravaActivity:
    """Fetch one Strava activity in detail and convert it for storage.

    Args:
        activity: The Strava summary activity.
        user_id: The user the activity belongs to.
        user_privacy_settings: The user's privacy defaults.
        timezone: The timezone for an activity with no GPS track.
        strava_client: A client authenticated as the user.
        user_integrations: The user's integration settings.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        The activity to store, its stream data and its laps.

    Raises:
        TooManyRequestsError: When Strava's rate limit is active or was just hit.
        DependencyFailedError: When Strava cannot return the activity, or returns it without an id, start date,
            sport type or elapsed time.
    """
    strava_activity_id = _strava_activity_id(activity, user_id)
    client_id = strava_client_service.get_client_id(user_integrations)
    strava_client_service.raise_if_rate_limit_active(client_id, user_id, rate_limits)

    try:
        detailed_activity = strava_client_service.call_strava(
            lambda client: client.get_activity(strava_activity_id),
            strava_client,
            user_id,
            user_integrations,
            rate_limits,
        )
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        strava_client_service.raise_if_rate_limited(err, client_id, rate_limits)
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava activity") from err

    # Parse start and end dates
    start_date_parsed = core_timezone.to_utc_second(detailed_activity.start_date)
    if start_date_parsed is None:
        # stravalib types start_date as optional; without it there is nothing to
        # anchor the activity to, and every downstream consumer (dedup by start
        # time, end-time derivation) requires it.
        logger.warning(
            "Strava activity has no start date, skipping",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
        )
        raise core_exceptions.DependencyFailedError("Strava activity has no start date")

    # stravalib types sport_type as optional too; without it the activity has no type to be stored as.
    if detailed_activity.sport_type is None:
        logger.warning(
            "Strava activity has no sport type, skipping",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
        )
        raise core_exceptions.DependencyFailedError("Strava activity has no sport type")
    sport_type = detailed_activity.sport_type.root

    # Without an elapsed time the activity has no end to be stored with.
    if detailed_activity.elapsed_time is None:
        logger.warning(
            "Strava activity has no elapsed time, skipping",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
        )
        raise core_exceptions.DependencyFailedError("Strava activity has no elapsed time")

    # Ensure activity.elapsed_time is a numerical value
    total_elapsed_time = (
        detailed_activity.elapsed_time.total_seconds()
        if isinstance(detailed_activity.elapsed_time, timedelta)
        else detailed_activity.elapsed_time
    )

    total_timer_time = (
        detailed_activity.moving_time.total_seconds()
        if isinstance(detailed_activity.moving_time, timedelta)
        else detailed_activity.moving_time
    )

    end_date_parsed = start_date_parsed + timedelta(seconds=total_elapsed_time)

    # Initialize location variables
    city, town, country = None, None, None
    if detailed_activity.location_city is not None:
        city = detailed_activity.location_city
    if detailed_activity.location_state is not None:
        town = detailed_activity.location_state
    if detailed_activity.location_country is not None:
        country = detailed_activity.location_country

    # Fetch and process activity streams
    (
        lat_lon_waypoints,
        is_lat_lon_set,
        ele_waypoints,
        is_elevation_set,
        hr_waypoints,
        is_heart_rate_set,
        cad_waypoints,
        is_cadence_set,
        power_waypoints,
        is_power_set,
        vel_waypoints,
        is_velocity_set,
    ) = fetch_and_process_activity_streams(
        strava_client,
        strava_activity_id,
        user_id,
        user_integrations,
        rate_limits,
    )

    ele_gain, ele_loss = None, None
    # Calculate elevation gain and loss
    if ele_waypoints:
        gains, losses = activities_computation.elevation_steps([point["ele"] for point in ele_waypoints])
        ele_gain, ele_loss = sum(gains), sum(losses)

        if detailed_activity.total_elevation_gain is not None:
            ele_gain = round(detailed_activity.total_elevation_gain)

    # Get average and max speed
    avg_speed = None
    if detailed_activity.average_speed is not None:
        avg_speed = detailed_activity.average_speed

    max_speed = None
    if detailed_activity.max_speed is not None:
        max_speed = detailed_activity.max_speed

    # Calculate average pace
    average_pace = 1 / avg_speed if avg_speed else None

    avg_hr, max_hr = None, None
    # Get average and max heart rate
    if detailed_activity.average_heartrate is not None:
        avg_hr = detailed_activity.average_heartrate

    if detailed_activity.max_heartrate is not None:
        max_hr = detailed_activity.max_heartrate

    avg_cadence, max_cadence = None, None
    # Calculate average and maximum cadence
    if cad_waypoints:
        max_cadence = max(point["cad"] for point in cad_waypoints)
        if detailed_activity.average_cadence is not None:
            avg_cadence = detailed_activity.average_cadence
        else:
            avg_cadence = _mean_without_zeros(cad_waypoints, "cad", _pause_threshold(cad_waypoints))

    activity_type = activity_constants.define_activity_type(sport_type)
    if activity_constants.is_running_cadence_type(activity_type):
        avg_cadence = activities_computation.double_running_cadence(avg_cadence)
        max_cadence = activities_computation.double_running_cadence(max_cadence)
        cad_waypoints = [{**point, "cad": round(point["cad"] * 2)} for point in cad_waypoints]

    # Get average and max power
    avg_power = None
    if detailed_activity.average_watts is not None:
        avg_power = detailed_activity.average_watts

    max_power = None
    if detailed_activity.max_watts is not None:
        max_power = detailed_activity.max_watts

    # Calculate normalized power
    np = None
    if power_waypoints:
        np = _normalized_power(power_waypoints, _pause_threshold(power_waypoints))

    # The map stream is stored when Strava gives the activity a start point; the samples and the start point follow it.
    is_map_set = detailed_activity.start_latlng is not None
    start_point = lat_lon_waypoints[0] if is_map_set and lat_lon_waypoints else None

    # List of conditions, stream types, and corresponding waypoints
    stream_data: list[StravaStreamEntry] = [
        (is_heart_rate_set, activity_streams_constants.STREAM_TYPE_HR, hr_waypoints),
        (is_power_set, activity_streams_constants.STREAM_TYPE_POWER, power_waypoints),
        (is_cadence_set, activity_streams_constants.STREAM_TYPE_CADENCE, cad_waypoints),
        (is_elevation_set, activity_streams_constants.STREAM_TYPE_ELEVATION, ele_waypoints),
        (is_velocity_set, activity_streams_constants.STREAM_TYPE_SPEED, vel_waypoints),
        (is_map_set, activity_streams_constants.STREAM_TYPE_MAP, lat_lon_waypoints),
    ]

    gear_id: uuid.UUID | None = None

    if user_integrations.strava_sync_gear and detailed_activity.gear_id is not None:
        # set the gear id for the activity
        with core_database.SessionLocal() as db:
            gear = gears_integration.get_gear_by_strava_id(detailed_activity.gear_id, user_id, db)

        # set the gear id for the activity
        if gear is not None:
            gear_id = gear.id

    if gear_id is None:
        with core_database.SessionLocal() as db:
            gear_id = users_default_gear_integration.get_default_gear_for_activity_type(user_id, activity_type, db)

    if activity_type != 3 and activity_type != 7 and is_lat_lon_set:
        timezone = core_timezone.from_lat_lon(
            lat_lon_waypoints[0]["lat"],
            lat_lon_waypoints[0]["lon"],
            timezone,
        )

    # Create the activity object
    activity_to_store = activity_contracts.ActivityCore(
        user_id=user_id,
        name=detailed_activity.name or activity_constants.DEFAULT_ACTIVITY_NAME,
        distance=round(detailed_activity.distance) if detailed_activity.distance else 0,
        description=detailed_activity.description,
        activity_type=activity_constants.ActivityType.from_stored(activity_type),
        start_time=start_date_parsed,
        end_time=end_date_parsed,
        timezone=timezone,
        total_elapsed_time=total_elapsed_time,
        total_timer_time=total_timer_time,
        city=city,
        town=town,
        country=country,
        elevation_gain=round(ele_gain) if ele_gain else None,
        elevation_loss=round(ele_loss) if ele_loss else None,
        pace=average_pace,
        average_speed=avg_speed,
        max_speed=max_speed,
        average_power=round(avg_power) if avg_power else None,
        max_power=max_power,
        normalized_power=round(np) if np else None,
        average_hr=round(avg_hr) if avg_hr else None,
        max_hr=max_hr,
        average_cad=round(avg_cadence) if avg_cadence else None,
        max_cad=round(max_cadence) if max_cadence else None,
        calories=round(detailed_activity.calories) if detailed_activity.calories is not None else None,
        gear_id=gear_id,
        strava_gear_id=detailed_activity.gear_id,
        strava_activity_id=strava_activity_id,
        visibility=users_privacy_settings_integration.resolve_visibility(
            user_privacy_settings.default_activity_visibility
        ),
        hide_start_time=user_privacy_settings.hide_activity_start_time or False,
        hide_location=user_privacy_settings.hide_activity_location or False,
        hide_map=user_privacy_settings.hide_activity_map or False,
        hide_hr=user_privacy_settings.hide_activity_hr or False,
        hide_power=user_privacy_settings.hide_activity_power or False,
        hide_cadence=user_privacy_settings.hide_activity_cadence or False,
        hide_elevation=user_privacy_settings.hide_activity_elevation or False,
        hide_speed=user_privacy_settings.hide_activity_speed or False,
        hide_pace=user_privacy_settings.hide_activity_pace or False,
        hide_laps=user_privacy_settings.hide_activity_laps or False,
        hide_workout_sets_steps=user_privacy_settings.hide_activity_workout_sets_steps or False,
        hide_gear=user_privacy_settings.hide_activity_gear or False,
        start_latitude=start_point["lat"] if start_point else None,
        start_longitude=start_point["lon"] if start_point else None,
    )

    # Fetch and process activity laps
    laps = fetch_and_process_activity_laps(
        strava_client,
        strava_activity_id,
        user_id,
        stream_data,
        user_integrations,
        rate_limits,
    )

    # Return the activity and stream data
    return {
        "activity_to_store": activity_to_store,
        "stream_data": stream_data,
        "laps": laps,
    }


#: The samples channel and the waypoint key of each stream the samples hold, by stream type.
_SAMPLE_CHANNELS: dict[int, tuple[str, str]] = {
    activity_streams_constants.STREAM_TYPE_HR: ("heart_rate", "hr"),
    activity_streams_constants.STREAM_TYPE_POWER: ("power", "power"),
    activity_streams_constants.STREAM_TYPE_CADENCE: ("cadence", "cad"),
    activity_streams_constants.STREAM_TYPE_ELEVATION: ("elevation", "ele"),
    activity_streams_constants.STREAM_TYPE_SPEED: ("speed", "vel"),
}


def _parsed_samples(stream_data: list[StravaStreamEntry]) -> activity_streams_contracts.ParsedSamples | None:
    """Merge the set streams onto one timeline of samples, each channel holding the values its stream stores.

    Every stream is cut from the same time stream, so the timeline is the seconds any stream has a point at, in
    milliseconds from the activity start. A channel no set stream feeds is ``None``; a second where a stream has no
    point, such as a heart-rate dropout, is ``None`` in its channel. Pace has no channel: it is derived from speed.

    Args:
        stream_data: ``(is_set, stream_type, waypoints)`` tuples; only set streams are merged.

    Returns:
        The samples, or ``None`` when no set stream has a point.
    """
    by_type = {stream_type: waypoints for is_set, stream_type, waypoints in stream_data if is_set}
    seconds = sorted(
        {
            point["time"]
            for stream_type in (*_SAMPLE_CHANNELS, activity_streams_constants.STREAM_TYPE_MAP)
            for point in by_type.get(stream_type, [])
        }
    )
    if not seconds:
        return None
    index = {second: i for i, second in enumerate(seconds)}

    def channel(stream_type: int, key: str) -> list[float | None] | None:
        """Lay one stream's values on the timeline.

        Args:
            stream_type: The stream type.
            key: The waypoint key the stream stores its value under.

        Returns:
            The values, or ``None`` when the stream is not set or has no point.
        """
        points = by_type.get(stream_type)
        if not points:
            return None
        values: list[float | None] = [None] * len(seconds)
        for point in points:
            values[index[point["time"]]] = point[key]
        return values

    latitude = channel(activity_streams_constants.STREAM_TYPE_MAP, "lat")
    longitude = channel(activity_streams_constants.STREAM_TYPE_MAP, "lon")
    return activity_streams_contracts.ParsedSamples(
        offsets_ms=[round(second * 1000) for second in seconds],
        latitude=latitude,
        longitude=longitude,
        **{name: channel(stream_type, key) for stream_type, (name, key) in _SAMPLE_CHANNELS.items()},
    )


def save_activity_streams_laps(
    activity: activity_contracts.ActivityCore,
    stream_data: list[StravaStreamEntry],
    laps: list[StravaLap] | None,
    db: Session,
) -> activity_schema.ActivityRead:
    """Persist a Strava-parsed activity through the canonical ingestion seam.

    Strava is a thin adapter: it builds the
    format-agnostic :class:`~modules.activities.activity.schema.ParsedActivity`
    from the parse result and delegates persistence + ``activity.created``
    publication to
    :func:`~modules.activities.activity.activity_integration.store_parsed_activity`,
    instead of calling ``create_activity`` and the stream/lap CRUD directly. The
    notification, thumbnail, and HR-zone subscribers react to the published event.

    Args:
        activity: The parsed Strava activity to persist.
        stream_data: ``(is_set, stream_type, waypoints)`` tuples; only set streams
            become the stored samples.
        laps: Parsed lap dicts, or ``None`` when the activity has no laps.
        db: Database session.

    Returns:
        The created activity schema.
    """
    parsed = activity_contracts.ParsedActivity(
        activity=activity,
        components={"samples": _parsed_samples(stream_data), "laps": laps},
        source=activity_contracts.ImportSource(
            kind="strava",
            provider_activity_id=activity.strava_activity_id,
            precedence=activity_constants.SOURCE_PRECEDENCE_API,
        ),
    )

    # Persist + publish ``activity.created`` via the canonical seam. The seam marks
    # duplicate start times hidden and forwards that to the notification subscriber.
    stored = activity_integration.store_parsed_activity(parsed, db)
    db.commit()
    logger.debug(
        "Strava activity stored",
        extra=core_logger.context(user_id=activity.user_id, strava_activity_id=activity.strava_activity_id),
    )
    return stored


def _summary_window(activity: SummaryActivity) -> tuple[int, datetime, datetime] | None:
    """Read from a listed activity when it ran and its sport, without fetching it.

    Args:
        activity: The Strava summary activity.

    Returns:
        The stored sport type, the start and the end, or ``None`` when the listing lacks any of them.
    """
    start = core_timezone.to_utc_second(activity.start_date)
    elapsed = activity.elapsed_time
    if start is None or elapsed is None or activity.sport_type is None:
        return None
    seconds = elapsed.total_seconds() if isinstance(elapsed, timedelta) else float(elapsed)
    return activity_constants.define_activity_type(activity.sport_type.root), start, start + timedelta(seconds=seconds)


def process_activity(
    activity: SummaryActivity,
    user_id: uuid.UUID,
    user_privacy_settings: users_privacy_settings_schema.UserPrivacySettingsRead,
    timezone: str,
    strava_client: Client,
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> activity_schema.ActivityRead | None:
    """Parse one Strava activity and store it, unless it is already stored.

    The Strava calls inside :func:`parse_activity` run with no session open. The
    check for what the user has already and the store each use a short session, and the store
    publishes ``activity.created`` on this worker thread, where its subscribers
    run inline without touching the request path. The store is idempotent on the
    activity's source, so two workers racing on one activity store it once.

    Args:
        activity: The Strava summary activity.
        user_id: The user the activity belongs to.
        user_privacy_settings: The user's privacy defaults.
        timezone: The timezone for an activity with no GPS track.
        strava_client: A client authenticated as the user.
        user_integrations: The user's integration settings.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        The stored activity, or ``None`` when it was already stored.

    Raises:
        DependencyFailedError: When Strava sent the activity without an id.
    """
    strava_activity_id = _strava_activity_id(activity, user_id)
    window = _summary_window(activity)
    with core_database.SessionLocal() as db:
        if window is None:
            already_known = activity_ingestion_integration.is_provider_activity_stored(
                user_id, activity_constants.SOURCE_KIND_STRAVA, strava_activity_id, db
            )
        else:
            # The listing says when the activity ran and what sport it was, which is enough to know the user has the
            # effort already, from a source that ranks above Strava's: then nothing is fetched.
            sport, start, end = window
            already_known = activity_ingestion_integration.attach_strava_activity_if_known(
                user_id, strava_activity_id, sport, start, end, db
            )
        db.commit()
    if already_known:
        logger.debug(
            "Strava activity already exists, or is of an effort the user has, skipping",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
        )
        return None

    logger.debug(
        "Strava activity will be processed",
        extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
    )

    parsed_activity = parse_activity(
        activity, user_id, user_privacy_settings, timezone, strava_client, user_integrations, rate_limits
    )

    with core_database.SessionLocal() as db:
        return save_activity_streams_laps(
            parsed_activity["activity_to_store"],
            parsed_activity["stream_data"],
            parsed_activity["laps"],
            db,
        )


def fetch_and_process_activity_streams(
    strava_client: Client,
    strava_activity_id: int,
    user_id: uuid.UUID,
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> StravaStreams:
    """Fetch an activity's streams from Strava and convert them to waypoint lists.

    Args:
        strava_client: A client authenticated as the user.
        strava_activity_id: The Strava activity id.
        user_id: The user the activity belongs to.
        user_integrations: The user's integration settings.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        A flat tuple of each stream's waypoints and whether it is present. All empty when the activity has no
        streams.

    Raises:
        TooManyRequestsError: When Strava's rate limit is active or was just hit.
        DependencyFailedError: When Strava cannot return the streams.
    """
    client_id = strava_client_service.get_client_id(user_integrations)
    strava_client_service.raise_if_rate_limit_active(client_id, user_id, rate_limits)

    try:
        streams = strava_client_service.call_strava(
            lambda client: client.get_activity_streams(
                strava_activity_id,
                types=[
                    "latlng",
                    "altitude",
                    "time",
                    "heartrate",
                    "cadence",
                    "watts",
                    "velocity_smooth",
                ],
            ),
            strava_client,
            user_id,
            user_integrations,
            rate_limits,
        )
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        strava_client_service.raise_if_rate_limited(err, client_id, rate_limits)
        # Streams simply don't exist for some activities (e.g. manually added ones from
        # Apple Health have no GPS/sensor streams); import the activity without them.
        if strava_client_service.is_strava_not_found_error(err):
            logger.debug(
                "No streams found for Strava activity (no sensor data), continuing without streams",
                extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
            )
            return ([], False, [], False, [], False, [], False, [], False, [], False)
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava activity streams") from err

    def stream_data(name: str) -> list[float]:
        """Return a stream's values, or an empty list when Strava sent no such stream.

        Args:
            name: The stream's name, one whose values are numbers.

        Returns:
            The stream's values.
        """
        return list(streams[name].data or []) if name in streams else []

    time = stream_data("time")

    def waypoints(name: str, key: str) -> list[StravaWaypoint]:
        """Pair a stream's values with the time stream.

        Args:
            name: The stream's name, one whose values are numbers.
            key: The waypoint key each value is stored under.

        Returns:
            The waypoints, one per timestamp that has a value.
        """
        # A stream longer than the time stream has no timestamp for its extra points.
        return [{"time": t, key: value} for t, value in zip(time, stream_data(name), strict=False)]

    # Each ``latlng`` value is a ``[lat, lon]`` pair rather than a number.
    lat_lon_values: list[list[float]] = list(streams["latlng"].data or []) if "latlng" in streams else []
    lat_lon_waypoints: list[StravaWaypoint] = [
        {"time": t, "lat": value[0], "lon": value[1]} for t, value in zip(time, lat_lon_values, strict=False)
    ]
    raw_ele_waypoints = waypoints("altitude", "ele")
    smoothed_ele = activities_computation.smooth_elevation(
        [point["time"] for point in raw_ele_waypoints], [point["ele"] for point in raw_ele_waypoints]
    )
    ele_waypoints: list[StravaWaypoint] = [
        {"time": point["time"], "ele": ele} for point, ele in zip(raw_ele_waypoints, smoothed_ele, strict=True)
    ]
    # A heart rate of 0 is a sensor dropout, not a reading.
    hr_waypoints = [point for point in waypoints("heartrate", "hr") if point["hr"] != 0]
    cad_waypoints = waypoints("cadence", "cad")
    power_waypoints = waypoints("watts", "power")
    vel_waypoints = waypoints("velocity_smooth", "vel")

    return (
        lat_lon_waypoints,
        bool(lat_lon_waypoints),
        ele_waypoints,
        bool(ele_waypoints),
        hr_waypoints,
        bool(hr_waypoints),
        cad_waypoints,
        bool(cad_waypoints),
        power_waypoints,
        bool(power_waypoints),
        vel_waypoints,
        bool(vel_waypoints),
    )


def _lap_stream(filtered_stream_data: list[StravaStreamEntry], stream_type: int) -> list[StravaWaypoint] | None:
    """Return the waypoints of one stream type from a lap's slice of the streams, if it has them."""
    return next((points for _, stream_id, points in filtered_stream_data if stream_id == stream_type), None)


def fetch_and_process_activity_laps(
    strava_client: Client,
    strava_activity_id: int,
    user_id: uuid.UUID,
    stream_data: list[StravaStreamEntry],
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> list[StravaLap] | None:
    """Fetch an activity's laps from Strava and derive each lap's metrics.

    Args:
        strava_client: A client authenticated as the user.
        strava_activity_id: The Strava activity id.
        user_id: The user the activity belongs to.
        stream_data: ``(is_set, stream_type, waypoints)`` tuples the lap metrics are cut from.
        user_integrations: The user's integration settings.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        The converted laps, or ``None`` when Strava has none for the activity.

    Raises:
        TooManyRequestsError: When Strava's rate limit is active or was just hit.
        DependencyFailedError: When Strava cannot return the laps.
    """
    client_id = strava_client_service.get_client_id(user_integrations)
    strava_client_service.raise_if_rate_limit_active(client_id, user_id, rate_limits)

    try:
        laps = strava_client_service.call_strava(
            # stravalib pages laps lazily: listing them here makes the request inside the call, where its 401,
            # 404 and 429 are handled, not in the loop below.
            lambda client: list(client.get_activity_laps(strava_activity_id)),
            strava_client,
            user_id,
            user_integrations,
            rate_limits,
        )
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        strava_client_service.raise_if_rate_limited(err, client_id, rate_limits)
        # Laps don't exist for some activities; import the activity without them.
        if strava_client_service.is_strava_not_found_error(err):
            logger.debug(
                "No laps found for Strava activity, continuing without laps",
                extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
            )
            return None
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava activity laps") from err

    # The hysteresis runs once over the whole activity, so the laps' ascents and descents add up to the activity's.
    ele_stream_all = _lap_stream(stream_data, activity_streams_constants.STREAM_TYPE_ELEVATION) or []
    ele_gains, ele_losses = activities_computation.elevation_steps([point["ele"] for point in ele_stream_all])
    cad_gap = _pause_threshold(_lap_stream(stream_data, activity_streams_constants.STREAM_TYPE_CADENCE) or [])
    power_gap = _pause_threshold(_lap_stream(stream_data, activity_streams_constants.STREAM_TYPE_POWER) or [])

    # Create an array to store the processed laps
    laps_processed: list[StravaLap] = []

    # A lap owns its samples from its start index up to the next lap's start index, so the laps partition the
    # activity whether Strava gives consecutive laps a shared boundary index or adjacent ones; the last lap owns its
    # samples through its end index.
    owned_ends: list[int | None] = []
    for position, lap in enumerate(laps):
        following = laps[position + 1].start_index if position + 1 < len(laps) else None
        owned_ends.append(
            following if following is not None else (lap.end_index + 1 if lap.end_index is not None else None)
        )

    # Process the laps
    for lap, owned_end in zip(laps, owned_ends, strict=True):
        # A lap is stored at its start time, so one Strava sent without it is left out.
        if lap.start_date_local is None:
            logger.warning(
                "Strava lap has no start time, skipping it",
                extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
            )
            continue

        cad_avg, cad_max = None, None
        power_avg, power_max = None, None
        np = None
        ele_gain, ele_loss = None, None

        # The stream indexes cut the lap out of the activity's streams; a lap without them has no stream metrics.
        # An average also takes the next lap's first sample as the end of its last sample's time, which it does not
        # weigh, so the lap's last sample holds its time.
        filtered_stream_data: list[StravaStreamEntry] = []
        timed_stream_data: list[StravaStreamEntry] = []
        lap_range: tuple[int, int] | None = None
        if lap.start_index is not None and owned_end is not None:
            lap_range = (lap.start_index, owned_end)
            for enabled, stream_id, waypoints in stream_data:
                if enabled:
                    filtered_stream_data.append((enabled, stream_id, waypoints[lap.start_index : owned_end]))
                    timed_stream_data.append((enabled, stream_id, waypoints[lap.start_index : owned_end + 1]))

        lat_lon_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_MAP)

        cad_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_CADENCE)

        if cad_stream:
            avg = _mean_without_zeros(
                _lap_stream(timed_stream_data, activity_streams_constants.STREAM_TYPE_CADENCE) or cad_stream,
                "cad",
                cad_gap,
            )
            cad_avg = round(avg) if avg is not None else None
            cad_max = round(max(point["cad"] for point in cad_stream))

        power_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_POWER)

        if power_stream:
            timed_power = _lap_stream(timed_stream_data, activity_streams_constants.STREAM_TYPE_POWER) or power_stream
            avg = activities_computation.time_weighted_mean(
                [point["time"] for point in timed_power], [point["power"] for point in timed_power], power_gap
            )
            power_avg = round(avg) if avg is not None else None
            power_max = round(max(point["power"] for point in power_stream))
            np = _normalized_power(power_stream, power_gap)

        # The elevation steps confirmed at the lap's own samples, from the one activity-wide pass.
        if ele_stream_all and lap_range is not None:
            first, last = lap_range
            lap_gains = ele_gains[first:last]
            if lap_gains:
                ele_gain = sum(lap_gains)
                ele_loss = sum(ele_losses[first:last])

        laps_processed.append(
            {
                "start_time": lap.start_date_local.strftime("%Y-%m-%dT%H:%M:%S"),
                "start_position_lat": (lat_lon_stream[0]["lat"] if lat_lon_stream else None),
                "start_position_long": (lat_lon_stream[0]["lon"] if lat_lon_stream else None),
                "end_position_lat": (lat_lon_stream[-1]["lat"] if lat_lon_stream else None),
                "end_position_long": (lat_lon_stream[-1]["lon"] if lat_lon_stream else None),
                "total_elapsed_time": lap.elapsed_time,
                "total_timer_time": lap.moving_time,
                "total_distance": lap.distance,
                "avg_heart_rate": (round(lap.average_heartrate) if lap.average_heartrate else None),
                "max_heart_rate": (round(lap.max_heartrate) if lap.max_heartrate else None),
                "avg_cadence": cad_avg,
                "max_cadence": cad_max,
                "avg_power": power_avg,
                "max_power": power_max,
                "total_ascent": round(ele_gain) if ele_gain is not None else None,
                "total_descent": round(ele_loss) if ele_loss is not None else None,
                "normalized_power": round(np) if np else None,
                "enhanced_avg_pace": (
                    1 / lap.average_speed if lap.average_speed != 0 and lap.average_speed is not None else None
                ),
                "enhanced_avg_speed": lap.average_speed,
                "enhanced_max_pace": (1 / lap.max_speed if lap.max_speed != 0 and lap.max_speed is not None else None),
                "enhanced_max_speed": lap.max_speed,
            }
        )

    # Return the processed laps
    return laps_processed


def get_user_strava_activities_by_dates(
    user_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store one user's Strava activities recorded in a window.

    Refreshes the user's access token first when it is about to expire, so the
    scheduled per-user refresh also keeps tokens current and no separate pass over
    every user is needed.

    Args:
        user_id: The user to sync.
        start_date: Start of the window.
        end_date: End of the window.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        The activities stored from the window, or ``None`` when Strava is not linked or nothing came back.

    Raises:
        DomainError: When Strava rejects the request or the account is missing.
    """
    strava_client_service.refresh_user_strava_token(user_id, rate_limits)

    with core_database.SessionLocal() as db:
        user_integrations = strava_client_service.fetch_user_integrations_and_validate_token(user_id, db)

    if user_integrations is None:
        logger.debug("Strava not linked", extra=core_logger.context(user_id=user_id))
        return None

    logger.info("Started Strava activities processing", extra=core_logger.context(user_id=user_id))
    strava_client = strava_client_service.create_strava_client(user_integrations)
    processed = fetch_and_process_activities_by_dates(
        strava_client, start_date, end_date, user_id, user_integrations, rate_limits
    )

    logger.info(
        "Strava activities processed",
        extra=core_logger.context(user_id=user_id, count=len(processed or [])),
    )
    return processed
