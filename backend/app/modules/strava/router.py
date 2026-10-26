"""Strava routes: account linking, activity and gear sync, and gear CSV import."""

from datetime import date

from fastapi import APIRouter, Request, Security, UploadFile

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.schema as gears_schema
import modules.strava.constants as strava_constants
import modules.strava.dependencies as strava_dependencies
import modules.strava.gear_service as strava_gear_service
import modules.strava.link_service as strava_link_service
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service
import modules.strava.sync_service as strava_sync_service

# Define the API router
router = APIRouter()


@router.post(
    "/link",
    status_code=202,
    response_model=strava_schema.StravaSyncStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_link(
    request: Request,
    link: strava_schema.StravaLinkRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    oauth_states: strava_dependencies.StravaOAuthStateStoreDep,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Queue the exchange of a Strava authorization code for tokens.

    Poll ``GET /strava/sync/link`` for the outcome. A second request while one is
    pending is answered 409.
    """
    return strava_link_service.start_link(link, token_user_id, oauth_states, sync_states)


@router.post(
    "/activities",
    status_code=202,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def strava_retrieve_activities_days(
    request: Request,
    start_date: date,
    end_date: date,
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


@router.post(
    "/gear",
    status_code=202,
    response_model=strava_schema.StravaSyncStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def strava_retrieve_gear(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
    rate_limits: strava_dependencies.StravaRateLimitStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Queue a sync of the user's Strava gear; a background job runs it.

    Poll ``GET /strava/sync/gear`` for the outcome. A second request while one is
    pending is answered 409.
    """
    return strava_sync_service.request_gear_sync(token_user_id, sync_states, rate_limits, db)


@router.get(
    "/sync/{kind}",
    response_model=strava_schema.StravaSyncStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def strava_sync_status(
    kind: strava_constants.SyncKind,
    token_user_id: auth_dependencies.CurrentUserId,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Report where the authenticated user's queued link, gear sync or unlink is."""
    return strava_sync_service.get_sync_status(token_user_id, kind, sync_states)


@router.post(
    "/import/bikes",
    status_code=201,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_bikes_from_strava_export(
    request: Request,
    file: UploadFile,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Create the bikes listed in an uploaded Strava ``bikes.csv``."""
    strava_gear_service.import_gear(file, token_user_id, gears_schema.GearType.BIKE, db)


@router.post(
    "/import/shoes",
    status_code=201,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_shoes_from_strava_export(
    request: Request,
    file: UploadFile,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Create the shoes listed in an uploaded Strava ``shoes.csv``."""
    strava_gear_service.import_gear(file, token_user_id, gears_schema.GearType.SHOES, db)


@router.put(
    "/client",
    response_model=strava_schema.StravaDetail,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_set_user_client(
    request: Request,
    client: strava_schema.StravaClientCredentials,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> strava_schema.StravaDetail:
    """Store the user's Strava API client id and secret."""
    strava_service.set_client(token_user_id, client, db)
    return strava_schema.StravaDetail(detail="Strava client edited successfully")


@router.post(
    "/state",
    status_code=201,
    response_model=strava_schema.StravaState,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_begin_state(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    oauth_states: strava_dependencies.StravaOAuthStateStoreDep,
) -> strava_schema.StravaState:
    """Issue the one-time state that correlates the OAuth callback with the user.

    Replaces any state the user issued earlier.
    """
    return strava_schema.StravaState(state=strava_service.begin_state(token_user_id, oauth_states))


@router.delete(
    "/state",
    response_model=strava_schema.StravaDetail,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_clear_user_state(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    oauth_states: strava_dependencies.StravaOAuthStateStoreDep,
) -> strava_schema.StravaDetail:
    """Forget the user's pending OAuth state."""
    strava_service.clear_state(token_user_id, oauth_states)
    return strava_schema.StravaDetail(detail="Strava state cleared successfully")


@router.delete(
    "/link",
    status_code=202,
    response_model=strava_schema.StravaSyncStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_unlink(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
    rate_limits: strava_dependencies.StravaRateLimitStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Queue the disconnection of the user's Strava account; a background job runs it.

    The job revokes the authorization with Strava and deletes the activities and gear
    imported from it. Poll ``GET /strava/sync/unlink`` for the outcome.
    """
    return strava_sync_service.request_unlink(token_user_id, sync_states, rate_limits, db)
