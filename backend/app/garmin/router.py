import logging
from typing import Annotated
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

import session.security as session_security

import user_integrations.crud as user_integrations_crud

import garmin.utils as garmin_utils
import garmin.schema as garmin_schema
import garmin.activity_utils as garmin_activity_utils
import garmin.gear_utils as garmin_gear_utils

import websocket.schema as websocket_schema

import database

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.post(
    "/link",
)
async def garminconnect_link(
    garmin_user: garmin_schema.GarminLogin,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(database.get_db)],
    mfa_codes: Annotated[
        garmin_schema.MFACodeStore, Depends(garmin_schema.get_mfa_store)
    ],
    websocket_manager: Annotated[
        websocket_schema.WebSocketManager,
        Depends(websocket_schema.get_websocket_manager),
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
        Depends(session_security.get_user_id_from_access_token),
    ],
    mfa_codes: Annotated[
        garmin_schema.MFACodeStore, Depends(garmin_schema.get_mfa_store)
    ],
):
    # Store the MFA code
    mfa_codes.add_code(token_user_id, mfa_request.mfa_code)
    return {"message": "MFA code received successfully"}


@router.get(
    "/activities/days/{days}",
    status_code=202,
)
async def garminconnect_retrieve_activities_days(
    days: int,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    # db: Annotated[Session, Depends(database.get_db)],
    background_tasks: BackgroundTasks,
):
    # Process Garmin Connect activities in the background
    background_tasks.add_task(
        garmin_activity_utils.get_user_garminconnect_activities_by_days,
        (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        token_user_id,
    )

    # Return success message and status code 202
    logger.info(
        f"Garmin Connect activities will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Garmin Connect activities will be processed in the background for for {token_user_id}"
    }


@router.get("/gear", status_code=202)
async def garminconnect_retrieve_gear(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        garmin_gear_utils.get_user_gear,
        token_user_id,
    )

    # Return success message and status code 202
    logger.info(
        f"Garmin Connect gear will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Garmin Connect gear will be processed in the background for for {token_user_id}"
    }


@router.delete("/unlink")
async def garminconnect_unlink(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # unlink garmin connect account
    user_integrations_crud.unlink_garminconnect_account(token_user_id, db)

    # Return success message
    return {"detail": f"Garmin Connect unlinked for user {token_user_id} successfully"}
