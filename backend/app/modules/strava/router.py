"""Strava routes: account linking, activity and gear sync, and gear CSV import."""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Security, UploadFile

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.strava.gear_service as strava_gear_service
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service

# Define the API router
router = APIRouter()


@router.put(
    "/link",
    response_model=strava_schema.StravaDetail,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_link(
    request: Request,
    state: str,
    code: str,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
):
    """Exchange a Strava authorization code for tokens and link the account."""
    return strava_service.link_account(state, code, token_user_id, db)


@router.get(
    "/activities",
    status_code=202,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def strava_retrieve_activities_days(
    request: Request,
    start_date: date,
    end_date: date,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Strava sync of an explicit date range.

    Returns ``202`` with a job handle; poll ``GET /activities/ingestion-jobs/{job_id}``
    for the outcome. The range is fetched by a background job, never on this
    request or an API worker thread.
    """
    return strava_service.request_activities_sync(token_user_id, start_date, end_date, storage, db)


@router.get(
    "/gear",
    status_code=201,
    response_model=strava_schema.StravaDetail,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def strava_retrieve_gear(
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    background_tasks: BackgroundTasks,
) -> strava_schema.StravaDetail:
    """Queue a background import of the user's Strava gear."""
    background_tasks.add_task(strava_gear_service.get_user_gear, token_user_id)
    return strava_schema.StravaDetail(detail=f"Strava gear will be processed in the background for for {token_user_id}")


@router.post("/import/bikes", status_code=201, response_model=None)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_bikes_from_strava_export(
    request: Request,
    file: UploadFile,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
):
    """Create the bikes listed in an uploaded Strava ``bikes.csv``."""
    strava_gear_service.import_bikes(file, token_user_id, db)


@router.post("/import/shoes", status_code=201, response_model=None)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_shoes_from_strava_export(
    request: Request,
    file: UploadFile,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
):
    """Create the shoes listed in an uploaded Strava ``shoes.csv``."""
    strava_gear_service.import_shoes(file, token_user_id, db)


@router.put(
    "/client",
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_set_user_client(
    request: Request,
    client: strava_schema.StravaClient,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
):
    """Store the user's Strava API client id and secret."""
    strava_service.set_client(token_user_id, client.client_id, client.client_secret, db)
    return {f"Strava client for user {token_user_id} edited successfully"}


@router.put(
    "/state/{state}",
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_set_user_unique_state(
    request: Request,
    state: str | None,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
):
    """Store the one-time state that correlates the OAuth callback with the user."""
    strava_service.set_state(token_user_id, state, db)
    return {f"Strava state for user {token_user_id} edited successfully"}


@router.delete(
    "/unlink",
    response_model=strava_schema.StravaDetail,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_unlink(
    request: Request,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
):
    """Disconnect the user's Strava account and delete what was imported from it."""
    strava_service.unlink_account(token_user_id, db)
    return strava_schema.StravaDetail(detail=f"Strava unlinked for user {token_user_id} successfully")
