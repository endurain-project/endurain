from datetime import UTC, date, datetime
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.garmin.gear_utils as garmin_gear_utils
import modules.garmin.health_utils as garmin_health_utils
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.garmin.provider_registry as garmin_provider_registry
import modules.garmin.schema as garmin_schema
import modules.garmin.utils as garmin_utils
import modules.users.users_integrations.crud as user_integrations_crud
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


@router.post(
    "/link",
)
async def garminconnect_link(
    garmin_user: garmin_schema.GarminLogin,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_codes: Annotated[
        garmin_mfa_code_store.GarminMFACodeStore,
        Depends(garmin_mfa_code_store.get_garmin_mfa_code_store),
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
        garmin_user.is_cn,
    )

    # Return success message
    return {f"Garmin Connect linked for user {token_user_id} successfully"}


@router.post("/mfa")
async def garminconnect_mfa_code(
    mfa_request: garmin_schema.MFARequest,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    mfa_codes: Annotated[
        garmin_mfa_code_store.GarminMFACodeStore,
        Depends(garmin_mfa_code_store.get_garmin_mfa_code_store),
    ],
):
    # Store the MFA code
    mfa_codes.add_code(token_user_id, mfa_request.mfa_code)
    return {"message": "MFA code received successfully"}


@router.get(
    "/activities",
    status_code=202,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def garminconnect_retrieve_activities_days(
    request: Request,
    start_date: date,
    end_date: date,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Garmin Connect sync of an explicit date range.

    Returns ``202`` with a job handle; poll ``GET /activities/ingestion-jobs/{job_id}``
    for the outcome. The range is fetched by a background job, never on this
    request or an API worker thread.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")

    job = activity_ingestion_integration.request_provider_sync(
        token_user_id,
        garmin_provider_registry.PROVIDER_NAME,
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        storage,
        db,
    )
    logger.info(f"Garmin Connect activities queued for user {token_user_id}")
    return job


@router.get("/gear", status_code=202)
async def garminconnect_retrieve_gear(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        garmin_gear_utils.get_user_gear,
        token_user_id,
    )

    # Return success message and status code 202
    logger.info(f"Garmin Connect gear will be processed in the background for user {token_user_id}")
    return {"detail": f"Garmin Connect gear will be processed in the background for for {token_user_id}"}


@router.get(
    "/health",
    status_code=202,
)
async def garminconnect_retrieve_health_days(
    start_date: date,
    end_date: date,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    # db: Annotated[Session, Depends(core_database.get_db)],
    background_tasks: BackgroundTasks,
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)

    # Process Garmin Connect activities in the background
    background_tasks.add_task(
        garmin_health_utils.get_user_garminconnect_health_by_dates,
        start_datetime,
        end_datetime,
        token_user_id,
        ws_manager,
    )

    # Return success message and status code 202
    logger.info(f"Garmin Connect health data will be processed in the background for user {token_user_id}")
    return {"detail": f"Garmin Connect health data will be processed in the background for for {token_user_id}"}


@router.delete("/unlink")
async def garminconnect_unlink(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
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
