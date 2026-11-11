"""Strava routes: account linking, activity and gear sync, and gear CSV import."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, UploadFile, status

import core.date_range as core_date_range
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.location as core_location
import core.middleware_body_limit as core_middleware_body_limit
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
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
    status_code=status.HTTP_202_ACCEPTED,
    response_model=strava_schema.StravaSyncStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_link(
    request: Request,
    response: Response,
    link: strava_schema.StravaLinkRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    oauth_states: strava_dependencies.StravaOAuthStateStoreDep,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Queue the exchange of a Strava authorization code for tokens.

    Send the ``state``, ``code`` and ``scope`` Strava put on the callback. ``scope`` is the comma-separated
    list of permissions the user granted; a link whose grant lacks ``read``, ``profile:read_all`` or
    ``activity:read_all`` is refused with 400 and ``urn:endurain:error:provider-scope-insufficient`` before
    the code is exchanged. Poll ``GET /jobs/{job_id}`` for the outcome. A second request while one is
    pending is answered 409.
    """
    sync = strava_link_service.start_link(token_user_id, link, oauth_states, sync_states)
    core_location.set_job_location(
        response, request, sync.id, strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.LINK]
    )
    return sync


@router.post(
    "/activities",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def strava_retrieve_activities_days(
    request: Request,
    response: Response,
    start_date: date,
    end_date: date,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Strava sync of an explicit date range.

    Returns ``202`` with a job handle; poll ``GET /jobs/{job_id}``
    for the outcome. The range is fetched by a background job, never on this
    request or an API worker thread.
    """
    core_date_range.refuse_reversed_range(start_date, end_date)
    job = strava_sync_service.request_activities_sync(token_user_id, start_date, end_date, storage, db)
    activity_ingestion_integration.set_job_location(response, request, job)
    return job


@router.post(
    "/gear",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=strava_schema.StravaSyncStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def strava_retrieve_gear(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
    rate_limits: strava_dependencies.StravaRateLimitStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Queue a sync of the user's Strava gear; a background job runs it.

    Poll ``GET /jobs/{job_id}`` for the outcome. A second request while one is
    pending is answered 409.
    """
    sync = strava_sync_service.request_gear_sync(token_user_id, sync_states, rate_limits, db)
    core_location.set_job_location(
        response, request, sync.id, strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.GEAR]
    )
    return sync


@router.post(
    "/import/gear",
    status_code=status.HTTP_201_CREATED,
    response_model=strava_schema.StravaGearImportResult,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
    openapi_extra=core_middleware_body_limit.upload_limit(strava_constants.GEAR_CSV_MAX_BYTES),
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_gear_from_strava_export(
    request: Request,
    file: UploadFile,
    gear_type: Annotated[strava_schema.StravaGearImportType, Query(description="Which Strava export file is uploaded")],
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> strava_schema.StravaGearImportResult:
    """Create the gear listed in an uploaded Strava ``bikes.csv`` or ``shoes.csv`` and report how many."""
    return strava_schema.StravaGearImportResult(
        imported=strava_gear_service.import_gear(file, token_user_id, gears_schema.GearType[gear_type.name], db)
    )


@router.put(
    "/client",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"headers": core_openapi_contract.ETAG_HEADERS}},
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_set_user_client(
    request: Request,
    client: strava_schema.StravaClientCredentials,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> None:
    """Store the user's Strava API client id and secret.

    Args:
        request: The incoming request, read by the rate limiter.
        client: The Strava application's client id and secret.
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition, the ``integrations_version`` the client read.

    """
    version = strava_service.set_client(token_user_id, client, db, if_match=if_match)
    core_etag.set_etag(response, version)


@router.post(
    "/state",
    status_code=status.HTTP_201_CREATED,
    response_model=strava_schema.StravaState,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
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
    "/link",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=strava_schema.StravaSyncStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def strava_unlink(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    sync_states: strava_dependencies.StravaSyncStateStoreDep,
    rate_limits: strava_dependencies.StravaRateLimitStoreDep,
) -> strava_schema.StravaSyncStatus:
    """Queue the disconnection of the user's Strava account; a background job runs it.

    The job revokes the authorization with Strava and deletes the activities and gear
    imported from it. Poll ``GET /jobs/{job_id}`` for the outcome.
    """
    sync = strava_sync_service.request_unlink(token_user_id, sync_states, rate_limits, db)
    core_location.set_job_location(
        response, request, sync.id, strava_constants.SYNC_POLL_SECONDS[strava_constants.SyncKind.UNLINK]
    )
    return sync
