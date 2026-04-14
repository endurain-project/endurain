"""OneLapFit activity processing utilities."""

from datetime import datetime, timedelta, timezone
from typing import Optional
import tempfile
import os

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

import core.logger as core_logger
import core.config as core_config
import core.cryptography as core_cryptography

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud
import activities.activity.models as activities_models
import activities.activity.utils as activities_utils
import activities.activity_streams.crud as activity_streams_crud

import users.users_integrations.models as user_integrations_models
import users.users.crud as users_crud

import users.users_privacy_settings.crud as users_privacy_settings_crud
import users.users_privacy_settings.models as users_privacy_settings_models
import users.users_privacy_settings.utils as users_privacy_settings_utils

import fit.utils as fit_utils

import onelapfit.utils as onelapfit_utils

import websocket.manager as websocket_manager

from core.database import SessionLocal


async def fetch_and_process_activities(
    token: str,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    user_integrations: user_integrations_models.UsersIntegrations,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
    is_startup: bool = False,
    region: Optional[str] = None,
) -> int:
    """
    Fetch and process OneLapFit activities within date range.

    Args:
        token: OneLapFit access token
        start_date: Start datetime for activity search
        end_date: End datetime for activity search
        user_id: User ID
        user_integrations: User integrations record
        ws_manager: WebSocket manager for notifications
        db: Database session
        is_startup: Whether this is a startup sync
        region: OneLapFit region code; overrides user_integrations.onelapfit_region
            when provided (used when user_integrations is not available)

    Returns:
        Count of processed activities
    """
    onelapfit_activities = None
    if region is None:
        region = user_integrations.onelapfit_region if user_integrations else None

    # Convert dates to Unix timestamps
    start_time = int(start_date.timestamp())
    end_time = int(end_date.timestamp())

    try:
        activities_data = await onelapfit_utils.fetch_onelapfit_activities(
            token=token,
            start_time=start_time,
            end_time=end_time,
            region=region,
            page=0,
        )
        onelapfit_activities = activities_data
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error fetching OneLapFit activities: {str(err)}",
            "error",
            exc=err,
        )
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="Unable to fetch OneLapFit activities",
            ) from err
        return 0

    if not onelapfit_activities or not onelapfit_activities.get("days"):
        core_logger.print_to_log(
            f"User {user_id}: No new OneLapFit activities found"
        )
        return 0

    days = onelapfit_activities.get("days", {})
    # API returns days as a dict keyed by timestamp string; guard against unexpected list
    if not isinstance(days, dict):
        core_logger.print_to_log(
            f"User {user_id}: Unexpected days format (expected dict, got {type(days).__name__})",
            "warning",
        )
        return 0

    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return 0

    user_privacy_settings = (
        users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
    )

    processed_activities = []

    # Process each day's activities
    for day_timestamp, day_data in days.items():
        for activity_info in day_data.get("info", []):
            try:
                processed_activity = await process_activity(
                    activity_info=activity_info,
                    user_id=user_id,
                    user_privacy_settings=user_privacy_settings,
                    token=token,
                    user_integrations=user_integrations,
                    ws_manager=ws_manager,
                    db=db,
                )
                if processed_activity:
                    processed_activities.append(processed_activity)
            except Exception as err:
                core_logger.print_to_log(
                    f"User {user_id}: Error processing OneLapFit activity: {str(err)}",
                    "error",
                    exc=err,
                )
                continue

    return len(processed_activities) if processed_activities else 0


async def process_activity(
    activity_info: dict,
    user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    token: str,
    user_integrations: user_integrations_models.UsersIntegrations,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> Optional[activities_schema.Activity]:
    """
    Process a single OneLapFit activity and create/update database record.

    Args:
        activity_info: Activity data from OneLapFit API
        user_id: User ID
        user_privacy_settings: User privacy settings
        token: OneLapFit token
        user_integrations: User integrations record
        ws_manager: WebSocket manager
        db: Database session

    Returns:
        Created/updated Activity object or None if skipped
    """
    try:
        # Parse activity data
        activity_to_store = parse_activity(
            activity_info=activity_info,
            user_id=user_id,
            user_privacy_settings=user_privacy_settings,
            db=db,
        )

        if activity_to_store is None:
            return None

        # Create activity in database
        activity = await activities_crud.create_activity(
            activity=activity_to_store,
            websocket_manager=ws_manager,
            db=db,
        )

        # Download and parse FIT file
        try:
            fit_file_url = activity_info.get("fileAddr")
            if fit_file_url and activity.id:
                fit_content = await onelapfit_utils.download_fit_file(fit_file_url)

                # Save FIT content to a temporary file for parsing
                with tempfile.NamedTemporaryFile(
                    suffix=".fit", delete=False, mode="wb"
                ) as temp_fit_file:
                    temp_fit_file.write(fit_content)
                    temp_fit_path = temp_fit_file.name

                try:
                    # Parse FIT file to extract activity streams and metadata
                    parsed_fit_data = fit_utils.parse_fit_file(
                        temp_fit_path, db, activity_info.get("name", "Ride")
                    )

                    # Back-fill avg_speed and max_speed from the FIT session record,
                    # which is more accurate than the value calculated from the API JSON.
                    fit_sessions = parsed_fit_data.get("sessions", [])
                    if fit_sessions:
                        fit_session = fit_sessions[0]
                        fit_avg_speed = fit_session.get("avg_speed")
                        fit_max_speed = fit_session.get("max_speed")
                        if fit_avg_speed is not None or fit_max_speed is not None:
                            db_activity = (
                                db.query(activities_models.Activity)
                                .filter(
                                    activities_models.Activity.id == activity.id
                                )
                                .first()
                            )
                            if db_activity is not None:
                                if fit_avg_speed is not None:
                                    db_activity.average_speed = fit_avg_speed
                                if fit_max_speed is not None:
                                    db_activity.max_speed = fit_max_speed
                                db.commit()

                    # Extract and store activity streams
                    activity_streams = activities_utils.parse_activity_streams_from_file(
                        parsed_fit_data, activity.id
                    )

                    if activity_streams:
                        activity_streams_crud.create_activity_streams(
                            activity_streams, db
                        )
                finally:
                    # Clean up temporary FIT file
                    try:
                        os.unlink(temp_fit_path)
                    except Exception as err:
                        core_logger.print_to_log(
                            f"User {user_id}: Failed to delete temporary FIT file: {str(err)}",
                            "warning",
                        )
        except Exception as err:
            core_logger.print_to_log(
                f"User {user_id}: Failed to download/parse FIT file: {str(err)}",
                "warning",
            )

        # Notify via WebSocket
        try:
            await ws_manager.send_message(
                user_id=user_id,
                message={
                    "type": "activity_imported",
                    "activity_id": activity.id,
                    "name": activity.name,
                },
            )
        except Exception as err:
            core_logger.print_to_log(
                f"User {user_id}: Failed to send WebSocket notification: {str(err)}",
                "warning",
            )

        return activity
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error in process_activity: {str(err)}",
            "error",
            exc=err,
        )
        return None


def parse_activity(
    activity_info: dict,
    user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    db: Session,
) -> Optional[activities_schema.Activity]:
    """
    Parse OneLapFit activity data into Activity schema format.

    Args:
        activity_info: Raw activity info from OneLapFit API
        user_id: User ID
        user_privacy_settings: User privacy settings
        db: Database session

    Returns:
        Activity schema object ready for database insertion or None if invalid
    """
    try:
        # Extract basic activity info
        start_time = activity_info.get("start_time", 0)
        elapsed_time = activity_info.get("time", 0)  # total elapsed wall-clock time, in seconds
        moving_time = activity_info.get("total_time", 0)  # moving/active time, in seconds
        distance = activity_info.get("distance", 0)  # in meters
        elevation_gain = activity_info.get("elevation", 0)

        # Create datetime from Unix timestamp
        activity_date = datetime.fromtimestamp(start_time, tz=timezone.utc)
        end_date = datetime.fromtimestamp(start_time + elapsed_time, tz=timezone.utc)

        # Find timezone
        tz_str = core_config.TZ

        # OneLapFit is currently for cycling, so we always set it to "Ride"
        activity_type = activities_utils.define_activity_type("ride")

        # Calculate speed if available (in m/s for average_speed field)
        if moving_time > 0 and distance > 0:
            avg_speed = distance / moving_time  # m/s
        else:
            avg_speed = 0.0

        # Calculate pace (s/m) from average speed
        average_pace = 1 / avg_speed if avg_speed > 0 else None

        # Get power metrics if available
        avg_watts = activity_info.get("AP", 0) or None
        normalized_power = activity_info.get("NP", 0) or None
        calories = activity_info.get("cal", 0) or None

        # Check if activity already exists before creating
        onelapfit_id = activity_info.get("fileKey", "").replace(".fit", "")
        existing = activities_crud.get_activity_by_onelapfit_id_from_user_id(
            onelapfit_id, user_id, db
        )
        if existing:
            core_logger.print_to_log(
                f"User {user_id}: OneLapFit activity {onelapfit_id} already exists, skipping"
            )
            return None

        # Create Activity schema object
        activity_to_store = activities_schema.Activity(
            user_id=user_id,
            name=activity_info.get("name", f"Ride - {activity_date.strftime('%Y-%m-%d')}"),
            distance=int(distance),  # in meters
            activity_type=activity_type,
            start_time=activity_date.strftime("%Y-%m-%dT%H:%M:%S"),
            end_time=end_date.strftime("%Y-%m-%dT%H:%M:%S"),
            timezone=tz_str,
            total_elapsed_time=float(elapsed_time),  # in seconds
            total_timer_time=float(moving_time),  # in seconds
            elevation_gain=int(elevation_gain) if elevation_gain else None,
            elevation_loss=None,  # Not provided by OneLapFit
            pace=average_pace,
            average_speed=avg_speed if avg_speed > 0 else None,
            max_speed=None,  # Not provided by OneLapFit
            average_power=int(avg_watts) if avg_watts else None,
            max_power=None,  # Not provided by OneLapFit
            normalized_power=int(normalized_power) if normalized_power else None,
            average_hr=None,  # Not provided by OneLapFit
            max_hr=None,  # Not provided by OneLapFit
            average_cad=None,  # Not provided by OneLapFit
            max_cad=None,  # Not provided by OneLapFit
            calories=int(calories) if calories else None,
            visibility=users_privacy_settings_utils.visibility_to_int(
                user_privacy_settings.default_activity_visibility
            ),
            onelapfit_id=onelapfit_id,
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

        return activity_to_store
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error parsing OneLapFit activity: {str(err)}",
            "error",
            exc=err,
        )
        return None


async def retrieve_onelapfit_users_activities(is_startup: bool = False):
    """
    Loop over all users and fetch recent OneLapFit activities.

    Called by the scheduler every 15 minutes and once at startup.
    Uses start_time=epoch during startup to pull full history;
    otherwise fetches the last day.

    Args:
        is_startup: When True fetches all history and suppresses per-user exceptions.
    """
    with SessionLocal() as db:
        try:
            users = users_crud.get_all_users(db)

            if is_startup:
                # Fetch all history by starting from 10 years ago
                # (epoch 0 is rejected by the OneLapFit API as an invalid signature)
                calculated_start_date = datetime.now(timezone.utc) - timedelta(days=365 * 10)
            else:
                calculated_start_date = datetime.now(timezone.utc) - timedelta(days=1)
            calculated_end_date = datetime.now(timezone.utc)

            if users:
                for user in users:
                    try:
                        await get_user_onelapfit_activities_by_dates(
                            start_date=calculated_start_date,
                            end_date=calculated_end_date,
                            user_id=user.id,
                            ws_manager=None,
                            db=None,
                            is_startup=is_startup,
                        )
                    except HTTPException as err:
                        core_logger.print_to_log(
                            f"User {user.id}: Error processing OneLapFit activities: {str(err)}",
                            "error",
                            exc=err,
                        )
                        if not is_startup:
                            raise err
                    except Exception as err:
                        core_logger.print_to_log(
                            f"User {user.id}: Unexpected error processing OneLapFit activities: {str(err)}",
                            "error",
                            exc=err,
                        )
                        if not is_startup:
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Internal Server Error",
                            ) from err
        except HTTPException as err:
            core_logger.print_to_log(
                f"Error retrieving users for OneLapFit sync: {str(err)}",
                "error",
                exc=err,
            )
            if not is_startup:
                raise err
        except Exception as err:
            core_logger.print_to_log(
                f"Error retrieving users for OneLapFit sync: {str(err)}",
                "error",
                exc=err,
            )
            if not is_startup:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal Server Error",
                ) from err


async def get_user_onelapfit_activities_by_dates(
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    ws_manager: websocket_manager.WebSocketManager | None = None,
    db: Session = None,
    is_startup: bool = False,
) -> int | None:
    """
    Fetch and process OneLapFit activities for a single user between two dates.

    Opens its own DB session when none is provided (scheduler path).

    Args:
        start_date: Start of the date range.
        end_date: End of the date range.
        user_id: User to sync.
        ws_manager: Optional WebSocket manager (created if None).
        db: Optional DB session (created if None).
        is_startup: Suppress exceptions when True.

    Returns:
        Number of activities processed, or None.
    """
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    if ws_manager is None:
        ws_manager = websocket_manager.get_websocket_manager()

    try:
        # Validate the user has OneLapFit linked
        user_integrations = onelapfit_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        if user_integrations is None:
            return None

        # Decrypt token
        token = core_cryptography.decrypt_token_fernet(
            user_integrations.onelapfit_token
        )

        core_logger.print_to_log(
            f"User {user_id}: Started OneLapFit activities processing"
        )

        try:
            count = await fetch_and_process_activities(
                token=token,
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
                user_integrations=user_integrations,
                ws_manager=ws_manager,
                db=db,
                is_startup=is_startup,
            )

            core_logger.print_to_log(
                f"User {user_id}: {count} OneLapFit activities processed"
            )

            return count
        except HTTPException as err:
            core_logger.print_to_log(
                f"User {user_id}: Error processing OneLapFit activities: {str(err)}",
                "error",
                exc=err,
            )
            if not is_startup:
                raise err
        except Exception as err:
            core_logger.print_to_log(
                f"User {user_id}: Error processing OneLapFit activities: {str(err)}",
                "error",
                exc=err,
            )
            if not is_startup:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal Server Error",
                ) from err
    except HTTPException as err:
        core_logger.print_to_log(
            f"User {user_id}: Error getting user integrations: {str(err)}",
            "error",
            exc=err,
        )
        if not is_startup:
            raise err
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error getting user integrations: {str(err)}",
            "error",
            exc=err,
        )
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal Server Error",
            ) from err
    finally:
        if close_session:
            db.close()
