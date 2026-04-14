"""OneLapFit integration API routes."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

import auth.security as auth_security

import users.users_integrations.crud as user_integrations_crud

import onelapfit.utils as onelapfit_utils
import onelapfit.activity_utils as onelapfit_activity_utils
import onelapfit.schema as onelapfit_schema

import core.config as core_config
import core.cryptography as core_cryptography
import core.logger as core_logger
import core.database as core_database

import websocket.manager as websocket_manager

# Define the API router
router = APIRouter()


@router.put("/link")
async def onelapfit_link(
    credentials: onelapfit_schema.OneLapFitClient,
    background_tasks: BackgroundTasks,
    user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Link OneLapFit account by email and password.

    Args:
        credentials: Email and password for OneLapFit account
        user_id: Authenticated user ID
        db: Database session

    Returns:
        Success message or error
    """
    try:
        # Get or create user integrations
        user_integrations = (
            user_integrations_crud.get_user_integrations_by_user_id(user_id, db)
        )

        if user_integrations is None:
            user_integrations = (
                user_integrations_crud.create_user_integrations(
                    user_id=user_id,
                    db=db,
                )
            )

        # Login to OneLapFit
        token, region = await onelapfit_utils.login_onelapfit(
            email=credentials.email,
            password=credentials.password,
        )

        # Encrypt and store token
        encrypted_token = core_cryptography.encrypt_token_fernet(token)
        user_integrations_crud.link_onelapfit_account(
            user_integrations=user_integrations,
            token=encrypted_token,
            region=region,
            db=db,
        )

        core_logger.print_to_log(
            f"User {user_id}: OneLapFit account linked successfully"
        )

        # Kick off a full-history sync in the background so the user sees
        # their rides immediately after linking (10 years back covers any
        # realistic ride history; epoch 0 is rejected by the OneLapFit API).
        # db is intentionally omitted so the background task opens its own
        # session (the request-scoped session is closed before the task runs).
        background_tasks.add_task(
            onelapfit_activity_utils.get_user_onelapfit_activities_by_dates,
            start_date=datetime.now(timezone.utc) - timedelta(days=365 * 10),
            end_date=datetime.now(timezone.utc),
            user_id=user_id,
            is_startup=False,
        )

        return {
            "detail": f"OneLapFit linked successfully for user {user_id}"
        }
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Unable to link OneLapFit account: {err}",
            "error",
            exc=err,
        )

        # Clean up
        try:
            user_integrations_crud.unlink_onelapfit_account(user_id, db)
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=f"Unable to link OneLapFit account: {err}",
        ) from err


@router.get("/activities")
async def get_onelapfit_activities(
    user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    start_date: datetime = None,
    end_date: datetime = None,
    background_tasks: BackgroundTasks = None,
    ws_manager: Annotated[websocket_manager.WebSocketManager, Depends(websocket_manager.get_websocket_manager)] = None,
):
    """
    Fetch and sync OneLapFit activities for user.

    Args:
        start_date: Start date for activity search (default: 30 days ago)
        end_date: End date for activity search (default: now)
        user_id: Authenticated user ID
        db: Database session
        background_tasks: Background task queue
        ws_manager: WebSocket manager

    Returns:
        Status message
    """
    # Set default dates
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    try:
        # Get user integrations and token
        user_integrations = (
            onelapfit_utils.fetch_user_integrations_and_validate_token(
                user_id, db
            )
        )

        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OneLapFit not linked. Please link your OneLapFit account first.",
            )

        # Decrypt token
        token = core_cryptography.decrypt_token_fernet(
            user_integrations.onelapfit_token
        )

        # Add background task to fetch activities.
        # db is intentionally omitted so the background task opens its own
        # session (the request-scoped session is closed before the task runs).
        background_tasks.add_task(
            _fetch_activities_background,
            token=token,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            region=user_integrations.onelapfit_region,
            ws_manager=ws_manager,
        )

        return {
            "status": "Background task started",
            "message": "Fetching OneLapFit activities in background",
        }
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error in get_onelapfit_activities: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.delete("/unlink")
async def unlink_onelapfit(
    user_id: Annotated[int, Depends(auth_security.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Unlink OneLapFit account and delete all OneLapFit data.

    Args:
        user_id: Authenticated user ID
        db: Database session

    Returns:
        Success message
    """
    try:
        user_integrations_crud.unlink_onelapfit_account(user_id, db)

        core_logger.print_to_log(
            f"User {user_id}: OneLapFit account unlinked successfully"
        )

        return {
            "detail": f"OneLapFit unlinked successfully for user {user_id}"
        }
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error unlinking OneLapFit: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


async def _fetch_activities_background(
    token: str,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    region: str | None,
    ws_manager,
):
    """
    Background task to fetch and process OneLapFit activities.

    Opens its own database session so the request-scoped session
    (which is closed before BackgroundTasks run) is never used here.

    Args:
        token: OneLapFit access token
        start_date: Start date for activities
        end_date: End date for activities
        user_id: User ID
        region: OneLapFit region code
        ws_manager: WebSocket manager
    """
    try:
        with core_database.SessionLocal() as db:
            count = await onelapfit_activity_utils.fetch_and_process_activities(
                token=token,
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
                user_integrations=None,
                ws_manager=ws_manager,
                db=db,
                is_startup=False,
                region=region,
            )

        core_logger.print_to_log(
            f"User {user_id}: Imported {count} OneLapFit activities"
        )

        # Notify user via WebSocket
        await ws_manager.send_message(
            user_id=user_id,
            message={
                "type": "sync_complete",
                "count": count,
                "source": "onelapfit",
            },
        )
    except Exception as err:
        core_logger.print_to_log(
            f"User {user_id}: Error in background activity fetch: {err}",
            "error",
            exc=err,
        )

        # Notify user of error via WebSocket
        try:
            await ws_manager.send_message(
                user_id=user_id,
                message={
                    "type": "sync_error",
                    "source": "onelapfit",
                    "error": str(err),
                },
            )
        except Exception:
            pass
