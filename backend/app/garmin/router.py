from typing import Annotated
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone, date

import auth.security as auth_security

import users.users_integrations.crud as user_integrations_crud

import garmin.utils as garmin_utils
import garmin.schema as garmin_schema
import garmin.activity_utils as garmin_activity_utils
import garmin.health_utils as garmin_health_utils
import garmin.gear_utils as garmin_gear_utils

import websocket.manager as websocket_manager

import core.logger as core_logger

import core.database as core_database

# Define the API router
router = APIRouter()


@router.post(
    "/link",
)
async def garminconnect_link(
    garmin_user: garmin_schema.GarminLogin,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_codes: Annotated[
        garmin_schema.MFACodeStore, Depends(garmin_schema.get_mfa_store)
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    # Link Garmin Connect account
    await garmin_utils.link_garminconnect(
        token_user_id,
        garmin_user.username,
        garmin_user.password,
        db,
        mfa_codes,
        websocket_manager,
    )

    # Return success message
    return {f"Garmin Connect linked for user {token_user_id} successfully"}


@router.post("/mfa")
async def garminconnect_mfa_code(
    mfa_request: garmin_schema.MFARequest,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    mfa_codes: Annotated[
        garmin_schema.MFACodeStore, Depends(garmin_schema.get_mfa_store)
    ],
):
    # Store the MFA code
    mfa_codes.add_code(token_user_id, mfa_request.mfa_code)
    return {"message": "MFA code received successfully"}


@router.get(
    "/activities",
    status_code=202,
)
async def garminconnect_retrieve_activities_days(
    start_date: date,
    end_date: date,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    background_tasks: BackgroundTasks,
):
    start_datetime = datetime.combine(
        start_date, datetime.min.time(), tzinfo=timezone.utc
    )
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Process Garmin Connect activities in the background
    background_tasks.add_task(
        garmin_activity_utils.get_user_garminconnect_activities_by_dates,
        start_datetime,
        end_datetime,
        token_user_id,
        websocket_manager,
        db,
    )

    # Return success message and status code 202
    core_logger.print_to_log(
        f"Garmin Connect activities will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Garmin Connect activities will be processed in the background for for {token_user_id}"
    }


@router.get("/gear", status_code=202)
async def garminconnect_retrieve_gear(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        garmin_gear_utils.get_user_gear,
        token_user_id,
    )

    # Return success message and status code 202
    core_logger.print_to_log(
        f"Garmin Connect gear will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Garmin Connect gear will be processed in the background for for {token_user_id}"
    }


@router.get(
    "/health",
    status_code=202,
)
async def garminconnect_retrieve_health_days(
    start_date: date,
    end_date: date,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    # db: Annotated[Session, Depends(core_database.get_db)],
    background_tasks: BackgroundTasks,
):
    start_datetime = datetime.combine(
        start_date, datetime.min.time(), tzinfo=timezone.utc
    )
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Process Garmin Connect activities in the background
    background_tasks.add_task(
        garmin_health_utils.get_user_garminconnect_health_by_dates,
        start_datetime,
        end_datetime,
        token_user_id,
    )

    # Return success message and status code 202
    core_logger.print_to_log(
        f"Garmin Connect health data will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Garmin Connect health data will be processed in the background for for {token_user_id}"
    }


@router.delete("/unlink")
async def garminconnect_unlink(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # unlink garmin connect account
    user_integrations_crud.unlink_garminconnect_account(token_user_id, db)

    # Return success message
    return {"detail": f"Garmin Connect unlinked for user {token_user_id} successfully"}
