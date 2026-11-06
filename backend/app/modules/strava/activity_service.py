"""Strava activity sync: fetch a window, parse each activity with its streams and laps, and store it."""

from datetime import datetime, timedelta
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

#: One sample of a stream: its ``time`` in seconds and the stream's own values, such as ``lat`` and ``lon``.
type StravaWaypoint = dict[str, float]

#: One stream of an activity: whether it is stored, its stream type and its waypoints.
type StravaStreamEntry = tuple[bool, int, list[StravaWaypoint]]

#: Each stream's waypoints followed by whether Strava sent it: lat/lon, elevation, heart rate, cadence, power and
#: velocity, then the pace waypoints derived from velocity.
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
    list[StravaWaypoint],
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
    user_id: int,
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


def _strava_activity_id(activity: SummaryActivity, user_id: int) -> int:
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


def parse_activity(
    activity: SummaryActivity,
    user_id: int,
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
        logger.warning(
            "Error fetching detailed Strava activity",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
            exc_info=err,
        )
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
        pace_waypoints,
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
        ele_gain, ele_loss = activities_computation.compute_elevation_gain_and_loss(ele_waypoints)

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
        avg_cadence, max_cadence = activities_computation.calculate_avg_and_max(cad_waypoints, "cad")

        if detailed_activity.average_cadence is not None:
            avg_cadence = detailed_activity.average_cadence

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
        np = activities_computation.calculate_np(power_waypoints)

    # List of conditions, stream types, and corresponding waypoints
    stream_data: list[StravaStreamEntry] = [
        (is_heart_rate_set, activity_streams_constants.STREAM_TYPE_HR, hr_waypoints),
        (is_power_set, activity_streams_constants.STREAM_TYPE_POWER, power_waypoints),
        (is_cadence_set, activity_streams_constants.STREAM_TYPE_CADENCE, cad_waypoints),
        (is_elevation_set, activity_streams_constants.STREAM_TYPE_ELEVATION, ele_waypoints),
        (is_velocity_set, activity_streams_constants.STREAM_TYPE_SPEED, vel_waypoints),
        (is_velocity_set, activity_streams_constants.STREAM_TYPE_PACE, pace_waypoints),
        (detailed_activity.start_latlng is not None, activity_streams_constants.STREAM_TYPE_MAP, lat_lon_waypoints),
    ]

    gear_id = None

    if user_integrations.strava_sync_gear and detailed_activity.gear_id is not None:
        # set the gear id for the activity
        with core_database.SessionLocal() as db:
            gear = gears_integration.get_gear_by_strava_id(detailed_activity.gear_id, user_id, db)

        # set the gear id for the activity
        if gear is not None:
            gear_id = gear.id

    # Activity type
    activity_type = activity_constants.define_activity_type(sport_type)

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
            are persisted.
        laps: Parsed lap dicts, or ``None`` when the activity has no laps.
        db: Database session.

    Returns:
        The created activity schema.
    """
    parsed_streams = [
        activity_streams_contracts.ParsedStream(
            stream_type=stream_type,
            stream_waypoints=(
                activities_computation.smooth_elevation_stream(waypoints)
                if stream_type == activity_streams_constants.STREAM_TYPE_ELEVATION
                else waypoints
            ),
        )
        for is_set, stream_type, waypoints in (stream_data or [])
        if is_set
    ]
    parsed = activity_contracts.ParsedActivity(
        activity=activity,
        components={"streams": parsed_streams, "laps": laps},
        source=activity_contracts.ImportSource(
            kind="strava",
            provider_activity_id=activity.strava_activity_id,
            dedup_key=(f"strava:{activity.strava_activity_id}" if activity.strava_activity_id is not None else None),
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


def process_activity(
    activity: SummaryActivity,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UserPrivacySettingsRead,
    timezone: str,
    strava_client: Client,
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> activity_schema.ActivityRead | None:
    """Parse one Strava activity and store it, unless it is already stored.

    The Strava calls inside :func:`parse_activity` run with no session open. The
    duplicate check and the store each use a short session, and the store
    publishes ``activity.created`` on this worker thread, where its subscribers
    run inline without touching the request path. The store is idempotent on the
    activity's ``dedup_key``, so two workers racing on one activity store it once.

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
    with core_database.SessionLocal() as db:
        already_stored = activity_integration.get_activity_by_strava_id(strava_activity_id, user_id, db) is not None
    if already_stored:
        logger.debug(
            "Strava activity already exists, skipping",
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
    user_id: int,
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
        A flat tuple of each stream's waypoints and whether it is present, ending
        with the pace waypoints. All empty when the activity has no streams.

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
            return ([], False, [], False, [], False, [], False, [], False, [], False, [])
        logger.warning(
            "Error fetching Strava activity streams",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
            exc_info=err,
        )
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
    ele_waypoints = waypoints("altitude", "ele")
    hr_waypoints = waypoints("heartrate", "hr")
    cad_waypoints = waypoints("cadence", "cad")
    power_waypoints = waypoints("watts", "power")
    vel_waypoints = waypoints("velocity_smooth", "vel")
    # Pace is derived from velocity; a standstill has pace 0.
    pace_waypoints: list[StravaWaypoint] = [
        {"time": point["time"], "pace": 1 / point["vel"] if point["vel"] != 0 else 0} for point in vel_waypoints
    ]

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
        pace_waypoints,
    )


def _lap_stream(filtered_stream_data: list[StravaStreamEntry], stream_type: int) -> list[StravaWaypoint] | None:
    """Return the waypoints of one stream type from a lap's slice of the streams, if it has them."""
    return next((points for _, stream_id, points in filtered_stream_data if stream_id == stream_type), None)


def fetch_and_process_activity_laps(
    strava_client: Client,
    strava_activity_id: int,
    user_id: int,
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
            lambda client: client.get_activity_laps(strava_activity_id),
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
        logger.warning(
            "Error fetching Strava activity laps",
            extra=core_logger.context(user_id=user_id, strava_activity_id=strava_activity_id),
            exc_info=err,
        )
        raise core_exceptions.DependencyFailedError("Not able to fetch Strava activity laps") from err

    # Create an array to store the processed laps
    laps_processed: list[StravaLap] = []

    # Process the laps
    for lap in laps:
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
        filtered_stream_data: list[StravaStreamEntry] = (
            [
                (enabled, stream_id, waypoints[lap.start_index : lap.end_index + 1])
                for enabled, stream_id, waypoints in stream_data
                if enabled
            ]
            if lap.start_index is not None and lap.end_index is not None
            else []
        )

        lat_lon_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_MAP)

        cad_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_CADENCE)

        if cad_stream:
            avg, peak = activities_computation.calculate_avg_and_max(cad_stream, "cad")
            cad_avg, cad_max = round(avg), round(peak)

        power_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_POWER)

        if power_stream:
            avg, peak = activities_computation.calculate_avg_and_max(power_stream, "power")
            power_avg, power_max = round(avg), round(peak)
            np = activities_computation.calculate_np(power_stream)

        ele_stream = _lap_stream(filtered_stream_data, activity_streams_constants.STREAM_TYPE_ELEVATION)

        if ele_stream:
            ele_gain, ele_loss = activities_computation.compute_elevation_gain_and_loss(ele_stream)

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
    user_id: int,
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
