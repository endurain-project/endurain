"""Garmin Connect routes: account linking, MFA, and activity, gear and health sync."""

from datetime import date
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.garmin.constants as garmin_constants
import modules.garmin.dependencies as garmin_dependencies
import modules.garmin.link_service as garmin_link_service
import modules.garmin.schema as garmin_schema
import modules.garmin.service as garmin_service
import modules.garmin.sync_service as garmin_sync_service

router = APIRouter()


@router.post(
    "/link",
    status_code=202,
    response_model=garmin_schema.GarminLinkStatus,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def garminconnect_link(
    request: Request,
    garmin_user: garmin_schema.GarminLogin,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    mfa_codes: garmin_dependencies.GarminMFACodeStoreDep,
    link_states: garmin_dependencies.GarminLinkStateStoreDep,
) -> garmin_schema.GarminLinkStatus:
    """Start linking a Garmin Connect account and return at once.

    The login runs in the background. Poll ``GET /garminconnect/link/status``: when it reports
    ``mfa_required``, submit the code to ``POST /garminconnect/mfa`` and keep polling until it
    reports ``completed`` or ``failed``. A second request while one is running is answered 409.
    """
    return garmin_link_service.start_link(token_user_id, garmin_user, mfa_codes, link_states)


@router.get(
    "/link/status",
    response_model=garmin_schema.GarminLinkStatus,
)
def garminconnect_link_status(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    link_states: garmin_dependencies.GarminLinkStateStoreDep,
) -> garmin_schema.GarminLinkStatus:
    """Report where the authenticated user's Garmin Connect link attempt is."""
    return garmin_link_service.get_link_status(token_user_id, link_states)


@router.post("/mfa", response_model=garmin_schema.GarminDetail)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def garminconnect_mfa_code(
    request: Request,
    mfa_request: garmin_schema.MFARequest,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    mfa_codes: garmin_dependencies.GarminMFACodeStoreDep,
    link_states: garmin_dependencies.GarminLinkStateStoreDep,
) -> garmin_schema.GarminDetail:
    """Hand the MFA code to the Garmin Connect login waiting for it."""
    return garmin_link_service.submit_mfa_code(token_user_id, mfa_request.mfa_code, mfa_codes, link_states)


@router.post(
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
    return garmin_sync_service.request_activities_sync(token_user_id, start_date, end_date, storage, db)


@router.post("/gear", status_code=202, response_model=garmin_schema.GarminSyncStatus)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def garminconnect_retrieve_gear(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    sync_states: garmin_dependencies.GarminSyncStateStoreDep,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect gear; a background job runs it.

    Poll ``GET /garminconnect/sync/gear`` for the outcome. A second request while one is
    pending is answered 409.
    """
    return garmin_sync_service.request_gear_sync(token_user_id, sync_states, db)


@router.post("/health", status_code=202, response_model=garmin_schema.GarminSyncStatus)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def garminconnect_retrieve_health_days(
    request: Request,
    start_date: date,
    end_date: date,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    sync_states: garmin_dependencies.GarminSyncStateStoreDep,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect health data for a date range.

    The range must not exceed 31 days; a background job runs it. Poll
    ``GET /garminconnect/sync/health`` for the outcome. A second request while one is pending is
    answered 409.
    """
    return garmin_sync_service.request_health_sync(token_user_id, start_date, end_date, sync_states, db)


@router.get("/sync/{kind}", response_model=garmin_schema.GarminSyncStatus)
def garminconnect_sync_status(
    kind: garmin_constants.SyncKind,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    sync_states: garmin_dependencies.GarminSyncStateStoreDep,
) -> garmin_schema.GarminSyncStatus:
    """Report where the authenticated user's queued gear or health sync is."""
    return garmin_sync_service.get_sync_status(token_user_id, kind, sync_states)


@router.delete("/link", response_model=garmin_schema.GarminDetail)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def garminconnect_unlink(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> garmin_schema.GarminDetail:
    """Unlink the user's Garmin Connect account."""
    return garmin_service.unlink_account(token_user_id, db)
