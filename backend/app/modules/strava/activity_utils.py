from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client
from stravalib.exc import AccessUnauthorized

import core.config as core_config
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.computation as activities_computation
import modules.gears.gear.crud as gears_crud
import modules.strava.utils as strava_utils
import modules.users.users.crud as users_crud
import modules.users.users_default_gear.utils as user_default_gear_utils
import modules.users.users_integrations.schema as user_integrations_schema
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_privacy_settings.utils as users_privacy_settings_utils
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def fetch_and_process_activities(
    strava_client: Client,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    user_integrations: user_integrations_schema.UsersIntegrationsRead,
) -> list[activity_schema.ActivityRead | None] | None:
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

    Returns:
        One entry per activity Strava returned (``None`` for one already stored),
        or ``None`` when Strava returned nothing or the user is rate limited.

    Raises:
        HTTPException: When Strava rejects the request or the user is missing.
    """
    # Check if we're currently rate-limited before making any Strava API calls
    if strava_utils.rate_limit_tracker.is_rate_limited():
        logger.warning(
            f"User {user_id}: Strava rate limit active, skipping activity fetch",
            extra=core_logger.context(console=True),
        )
        return None

    try:
        strava_activities = list(strava_client.get_activities(after=start_date, before=end_date))
    except AccessUnauthorized as auth_err:
        logger.error(f"User {user_id}: Authentication error with Strava: {auth_err!s}", exc_info=auth_err)
        raise HTTPException(
            status_code=(status.HTTP_424_FAILED_DEPENDENCY),
            detail=("Strava authentication failed. Please reconnect your Strava account."),
        ) from auth_err
    except HTTPException:
        raise
    except Exception as err:
        if strava_utils.is_strava_rate_limit_error(err):
            err_str = str(err).lower()
            is_long = "long" in err_str or ("daily" in err_str)
            strava_utils.rate_limit_tracker.mark_rate_limited(is_long_term=is_long)
            logger.warning(f"User {user_id}: Strava rate limit exceeded, skipping activity fetch")
            raise HTTPException(
                status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
                detail=("Strava API rate limit exceeded. Please try again later."),
            ) from err

        logger.error(f"User {user_id}: Error fetching Strava activities: {err!s}", exc_info=err)
        raise HTTPException(
            status_code=(status.HTTP_424_FAILED_DEPENDENCY),
            detail=("Not able to fetch Strava activities"),
        ) from err

    if not strava_activities:
        logger.info(f"User {user_id}: No new Strava activities found after {start_date}")
        return None

    with SessionLocal() as db:
        user = users_crud.get_user_by_id(user_id, db)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        user_privacy_settings = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)

    return [
        process_activity(
            activity,
            user_id,
            user_privacy_settings,
            strava_client,
            user_integrations,
        )
        for activity in strava_activities
    ]


def parse_activity(
    activity,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
    strava_client: Client,
    user_integrations: user_integrations_schema.UsersIntegrationsRead,
) -> dict:
    # Fallback for activities with no GPS track (indoor rides, treadmill runs):
    # prefer the athlete's own timezone over the server's, which is meaningless
    # for a user on another continent.
    with SessionLocal() as db:
        owner = users_crud.get_user_by_id(user_id, db)
    timezone = (owner.timezone if owner and owner.timezone else None) or core_config.settings.TZ

    # Check rate limit before detailed activity fetch
    if strava_utils.rate_limit_tracker.is_rate_limited():
        logger.warning(f"User {user_id}: Strava rate limit active, skipping activity parse")
        raise HTTPException(
            status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
            detail=("Strava API rate limit exceeded. Please try again later."),
        )

    # Get the detailed activity
    try:
        detailed_activity = strava_client.get_activity(activity.id)
    except Exception as err:
        # Check if this is a rate limit error
        if strava_utils.is_strava_rate_limit_error(err):
            err_str = str(err).lower()
            is_long = "long" in err_str or ("daily" in err_str)
            strava_utils.rate_limit_tracker.mark_rate_limited(is_long_term=is_long)
            raise HTTPException(
                status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
                detail=("Strava API rate limit exceeded. Please try again later."),
            ) from err
        # Log an error event if an exception occurred
        logger.error(f"User {user_id}: Error fetching detailed Strava activity {activity.id}: {err!s}", exc_info=err)
        raise HTTPException(
            status_code=(status.HTTP_424_FAILED_DEPENDENCY),
            detail=("Not able to fetch Strava activity"),
        ) from err

    # Parse start and end dates
    start_date_parsed = core_timezone.to_utc_second(detailed_activity.start_date)
    if start_date_parsed is None:
        # stravalib types start_date as optional; without it there is nothing to
        # anchor the activity to, and every downstream consumer (dedup by start
        # time, end-time derivation) requires it.
        logger.error(f"User {user_id}: Strava activity {activity.id} has no start date, skipping")
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Strava activity has no start date",
        )

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
        activity.id,
        user_id,
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
    average_pace = 1 / avg_speed if avg_speed != 0 else None

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
    stream_data = [
        (is_heart_rate_set, 1, hr_waypoints),
        (is_power_set, 2, power_waypoints),
        (is_cadence_set, 3, cad_waypoints),
        (is_elevation_set, 4, ele_waypoints),
        (is_velocity_set, 5, vel_waypoints),
        (is_velocity_set, 6, pace_waypoints),
        (detailed_activity.start_latlng is not None, 7, lat_lon_waypoints),
    ]

    gear_id = None

    if user_integrations.strava_sync_gear:
        # set the gear id for the activity
        with SessionLocal() as db:
            gear = gears_crud.get_gear_by_strava_id_from_user_id(detailed_activity.gear_id, user_id, db)

        # set the gear id for the activity
        if gear is not None:
            gear_id = gear.id

    # Activity type
    activity_type = activity_constants.define_activity_type(detailed_activity.sport_type.root)

    if gear_id is None:
        with SessionLocal() as db:
            gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(user_id, activity_type, db)

    if activity_type != 3 and activity_type != 7 and is_lat_lon_set:
        timezone = core_timezone.from_lat_lon(
            lat_lon_waypoints[0]["lat"],
            lat_lon_waypoints[0]["lon"],
            timezone,
        )

    # Create the activity object
    activity_to_store = activity_contracts.ActivityCore(
        user_id=user_id,
        name=detailed_activity.name,
        distance=round(detailed_activity.distance) if detailed_activity.distance else 0,
        description=detailed_activity.description,
        activity_type=activity_type,
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
        max_cad=max_cadence,
        calories=round(detailed_activity.calories),
        gear_id=gear_id,
        strava_gear_id=detailed_activity.gear_id,
        strava_activity_id=int(activity.id),
        visibility=users_privacy_settings_utils.visibility_to_int(user_privacy_settings.default_activity_visibility),
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
        activity.id,
        user_id,
        stream_data,
    )

    # Return the activity and stream data
    return {
        "activity_to_store": activity_to_store,
        "stream_data": stream_data,
        "laps": laps,
    }


def save_activity_streams_laps(
    activity: activity_contracts.ActivityCore,
    stream_data: list,
    laps: list[dict] | None,
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
    return stored


def process_activity(
    activity,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
    strava_client: Client,
    user_integrations: user_integrations_schema.UsersIntegrationsRead,
) -> activity_schema.ActivityRead | None:
    """Parse one Strava activity and store it, unless it is already stored.

    The Strava calls inside :func:`parse_activity` run with no session open. The
    duplicate check and the store each use a short session, and the store
    publishes ``activity.created`` on this worker thread, where its subscribers
    run inline without touching the request path.

    Args:
        activity (stravalib.model.SummaryActivity): The Strava summary activity.
        user_id: The user the activity belongs to.
        user_privacy_settings: The user's privacy defaults.
        strava_client: A client authenticated as the user.
        user_integrations: The user's integration settings.

    Returns:
        The stored activity, or ``None`` when it was already stored.
    """
    with SessionLocal() as db:
        already_stored = strava_utils.fetch_and_validate_activity(activity.id, user_id, db) is not None
    if already_stored:
        return None

    logger.info(f"User {user_id}: Strava activity {activity.id} will be processed")

    parsed_activity = parse_activity(activity, user_id, user_privacy_settings, strava_client, user_integrations)

    with SessionLocal() as db:
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
):
    # Check rate limit before fetching streams
    if strava_utils.rate_limit_tracker.is_rate_limited():
        logger.warning(f"User {user_id}: Strava rate limit active, skipping streams fetch")
        raise HTTPException(
            status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
            detail=("Strava API rate limit exceeded. Please try again later."),
        )

    # Get streams for the activity
    try:
        streams = strava_client.get_activity_streams(
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
        )
    except Exception as err:
        # Check if this is a rate limit error
        if strava_utils.is_strava_rate_limit_error(err):
            err_str = str(err).lower()
            is_long = "long" in err_str or ("daily" in err_str)
            strava_utils.rate_limit_tracker.mark_rate_limited(is_long_term=is_long)
            raise HTTPException(
                status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
                detail=("Strava API rate limit exceeded. Please try again later."),
            ) from err
        # Check if streams simply don't exist for this activity (e.g., manually
        # added activities from Apple Health have no GPS/sensor streams).
        # In that case return empty data so the activity can still be imported.
        if strava_utils.is_strava_not_found_error(err):
            logger.info(
                f"User {user_id}: No streams found for Strava activity {strava_activity_id} (activity has no sensor data). Continuing without streams."
            )
            return (
                [],
                False,  # lat_lon_waypoints, is_lat_lon_set
                [],
                False,  # ele_waypoints, is_elevation_set
                [],
                False,  # hr_waypoints, is_heart_rate_set
                [],
                False,  # cad_waypoints, is_cadence_set
                [],
                False,  # power_waypoints, is_power_set
                [],
                False,  # vel_waypoints, is_velocity_set
                [],  # pace_waypoints
            )
        # Log an error event if an exception occurred
        logger.error(
            f"User {user_id}: Error fetching Strava activity streams {strava_activity_id}: {err!s}", exc_info=err
        )
        raise HTTPException(
            status_code=(status.HTTP_424_FAILED_DEPENDENCY),
            detail=("Not able to fetch Strava activity streams"),
        ) from err

    # Extract data from streams
    lat_lon = streams["latlng"].data if "latlng" in streams else []
    lat_lon_waypoints = []
    is_lat_lon_set = False
    ele = streams["altitude"].data if "altitude" in streams else []
    ele_waypoints = []
    is_elevation_set = False
    time = streams["time"].data if "time" in streams else []
    hr = streams["heartrate"].data if "heartrate" in streams else []
    hr_waypoints = []
    is_heart_rate_set = False
    cad = streams["cadence"].data if "cadence" in streams else []
    cad_waypoints = []
    is_cadence_set = False
    power = streams["watts"].data if "watts" in streams else []
    power_waypoints = []
    is_power_set = False
    vel = streams["velocity_smooth"].data if "velocity_smooth" in streams else []
    vel_waypoints = []
    is_velocity_set = False
    pace_waypoints = []

    for i in range(len(lat_lon)):
        lat_lon_waypoints.append(
            {
                "time": time[i],
                "lat": lat_lon[i][0],
                "lon": lat_lon[i][1],
            }
        )
        is_lat_lon_set = True

    for i in range(len(ele)):
        ele_waypoints.append({"time": time[i], "ele": ele[i]})
        is_elevation_set = True

    for i in range(len(hr)):
        hr_waypoints.append({"time": time[i], "hr": hr[i]})
        is_heart_rate_set = True

    for i in range(len(cad)):
        cad_waypoints.append({"time": time[i], "cad": cad[i]})
        is_cadence_set = True

    for i in range(len(power)):
        power_waypoints.append({"time": time[i], "power": power[i]})
        is_power_set = True

    for i in range(len(vel)):
        # Append velocity to the velocity waypoints
        vel_waypoints.append({"time": time[i], "vel": vel[i]})

        # Calculate pace on-the-fly. If velocity is 0, pace is 0
        pace_calculation = 0
        if vel[i] != 0:
            pace_calculation = 1 / vel[i]

        # Append pace to the pace waypoints
        pace_waypoints.append({"time": time[i], "pace": pace_calculation})
        is_velocity_set = True

    return (
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
    )


def fetch_and_process_activity_laps(
    strava_client: Client,
    strava_activity_id: int,
    user_id: int,
    stream_data: list,
):
    # Fetch the activity laps
    try:
        laps = strava_client.get_activity_laps(strava_activity_id)
    except Exception as err:
        # Log an error event if an exception occurred
        logger.error(
            f"User {user_id}: Error fetching Strava activity laps for Strava activity {strava_activity_id}: {err!s}",
            exc_info=err,
        )
        # Return None to indicate the activity was not processed
        return None

    # Create an array to store the processed laps
    laps_processed = []

    # Process the laps
    for lap in laps:
        cad_avg, cad_max = None, None
        power_avg, power_max = None, None
        np = None
        ele_gain, ele_loss = None, None

        # filter the stream data based on the lap's start and end times
        filtered_stream_data = [
            (enabled, stream_id, waypoints[lap.start_index : lap.end_index + 1])
            for enabled, stream_id, waypoints in stream_data
            if enabled
        ]

        lat_lon_stream = next(
            (waypoints for enabled, stream_id, waypoints in filtered_stream_data if stream_id == 7),
            None,
        )

        cad_stream = next(
            (waypoints for enabled, stream_id, waypoints in filtered_stream_data if stream_id == 3),
            None,
        )

        if cad_stream:
            cad_avg, cad_max = activities_computation.calculate_avg_and_max(cad_stream, "cad")

        power_stream = next(
            (waypoints for enabled, stream_id, waypoints in filtered_stream_data if stream_id == 2),
            None,
        )

        if power_stream:
            power_avg, power_max = activities_computation.calculate_avg_and_max(power_stream, "power")
            np = activities_computation.calculate_np(power_stream)

        ele_stream = next(
            (waypoints for enabled, stream_id, waypoints in filtered_stream_data if stream_id == 4),
            None,
        )

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
                "avg_cadence": round(cad_avg) if cad_stream else None,
                "max_cadence": round(cad_max) if cad_stream else None,
                "avg_power": round(power_avg) if power_stream else None,
                "max_power": round(power_max) if power_stream else None,
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
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> list[activity_schema.ActivityRead | None] | None:
    """Fetch and store one user's Strava activities recorded in a window.

    Refreshes the user's access token first when it is about to expire, so the
    scheduled per-user refresh also keeps tokens current and no separate pass over
    every user is needed.

    Args:
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user to sync.

    Returns:
        The activities Strava returned, or ``None`` when Strava is not linked or
        nothing came back.

    Raises:
        HTTPException: When Strava rejects the request or the account is missing.
    """
    strava_utils.refresh_user_strava_token(user_id)

    with SessionLocal() as db:
        user_integrations = strava_utils.fetch_user_integrations_and_validate_token(user_id, db)

    if user_integrations is None:
        logger.info(f"User {user_id}: Strava not linked")
        return None

    logger.info(f"User {user_id}: Started Strava activities processing")
    strava_client = strava_utils.create_strava_client(user_integrations)
    processed = fetch_and_process_activities(strava_client, start_date, end_date, user_id, user_integrations)

    logger.info(f"User {user_id}: {len([a for a in processed or [] if a])} Strava activities processed")
    return processed
