"""Garmin Connect routes: account linking, MFA, and activity, gear and health sync."""

from datetime import date

from fastapi import APIRouter, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.location as core_location
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.garmin.constants as garmin_constants
import modules.garmin.dependencies as garmin_dependencies
import modules.garmin.link_service as garmin_link_service
import modules.garmin.schema as garmin_schema
import modules.garmin.service as garmin_service
import modules.garmin.sync_service as garmin_sync_service

router = APIRouter()


def _set_sync_location(response: Response, request: Request, sync: garmin_schema.GarminSyncStatus) -> None:
    """Name the status route of a queued gear or health sync on its ``202``.

    Args:
        response: The response of the route that queued the sync.
        request: The request, which resolves the status route's path.
        sync: The queued sync.
    """
    core_location.set_status_location(
        response, request, "garminconnect_sync_status", garmin_constants.SYNC_POLL_SECONDS, kind=sync.kind.value
    )


@router.post(
    "/link",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=garmin_schema.GarminLinkStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def garminconnect_link(
    request: Request,
    response: Response,
    garmin_user: garmin_schema.GarminLogin,
    token_user_id: auth_dependencies.CurrentUserId,
    mfa_codes: garmin_dependencies.GarminMFACodeStoreDep,
    link_states: garmin_dependencies.GarminLinkStateStoreDep,
) -> garmin_schema.GarminLinkStatus:
    """Start linking a Garmin Connect account and return at once.

    The login runs in the background. Poll ``GET /garmin/link/status``: when it reports
    ``mfa_required``, submit the code to ``POST /garmin/mfa`` and keep polling until it
    reports ``completed`` or ``failed``. A second request while one is running is answered 409 with a
    ``Content-Location`` naming the status.
    """
    link_status = garmin_link_service.start_link(token_user_id, garmin_user, mfa_codes, link_states)
    core_location.set_status_location(
        response, request, "garminconnect_link_status", garmin_constants.LINK_POLL_SECONDS
    )
    return link_status


@router.get(
    "/link/status",
    response_model=garmin_schema.GarminLinkStatus,
    responses={200: {"headers": core_location.POLLED_STATUS_HEADERS}},
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def garminconnect_link_status(
    token_user_id: auth_dependencies.CurrentUserId,
    link_states: garmin_dependencies.GarminLinkStateStoreDep,
    response: Response,
) -> garmin_schema.GarminLinkStatus:
    """Report where the authenticated user's Garmin Connect link attempt is.

    ``Retry-After`` says when to poll again while the attempt is not finished.
    """
    link_status = garmin_link_service.get_link_status(token_user_id, link_states)
    core_location.set_retry_after_while_running(response, link_status.status, garmin_constants.LINK_POLL_SECONDS)
    return link_status


@router.post(
    "/mfa",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def garminconnect_mfa_code(
    request: Request,
    mfa_request: garmin_schema.MFARequest,
    token_user_id: auth_dependencies.CurrentUserId,
    mfa_codes: garmin_dependencies.GarminMFACodeStoreDep,
    link_states: garmin_dependencies.GarminLinkStateStoreDep,
) -> None:
    """Hand the MFA code to the Garmin Connect login waiting for it."""
    garmin_link_service.submit_mfa_code(token_user_id, mfa_request.mfa_code, mfa_codes, link_states)


@router.post(
    "/activities",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def garminconnect_retrieve_activities_days(
    request: Request,
    response: Response,
    start_date: date,
    end_date: date,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Garmin Connect sync of an explicit date range.

    Returns ``202`` with a job handle; poll ``GET /activities/ingestion-jobs/{job_id}``
    for the outcome. The range is fetched by a background job, never on this
    request or an API worker thread.
    """
    job = garmin_sync_service.request_activities_sync(token_user_id, start_date, end_date, storage, db)
    activity_ingestion_integration.set_job_location(response, request, job)
    return job


@router.post(
    "/gear",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=garmin_schema.GarminSyncStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def garminconnect_retrieve_gear(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    sync_states: garmin_dependencies.GarminSyncStateStoreDep,
    rate_limits: garmin_dependencies.GarminRateLimitStoreDep,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect gear; a background job runs it.

    Poll ``GET /garmin/sync/gear`` for the outcome. A second request while one is
    pending is answered 409.
    """
    sync = garmin_sync_service.request_gear_sync(token_user_id, sync_states, rate_limits, db)
    _set_sync_location(response, request, sync)
    return sync


@router.post(
    "/health",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=garmin_schema.GarminSyncStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def garminconnect_retrieve_health_days(
    request: Request,
    response: Response,
    start_date: date,
    end_date: date,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    sync_states: garmin_dependencies.GarminSyncStateStoreDep,
    rate_limits: garmin_dependencies.GarminRateLimitStoreDep,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect health data for a date range.

    The range must not exceed 31 days; a background job runs it. Poll
    ``GET /garmin/sync/health`` for the outcome. A second request while one is pending is
    answered 409.
    """
    sync = garmin_sync_service.request_health_sync(token_user_id, start_date, end_date, sync_states, rate_limits, db)
    _set_sync_location(response, request, sync)
    return sync


@router.get(
    "/sync/{kind}",
    response_model=garmin_schema.GarminSyncStatus,
    responses={200: {"headers": core_location.POLLED_STATUS_HEADERS}},
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def garminconnect_sync_status(
    kind: garmin_constants.SyncKind,
    token_user_id: auth_dependencies.CurrentUserId,
    sync_states: garmin_dependencies.GarminSyncStateStoreDep,
    response: Response,
) -> garmin_schema.GarminSyncStatus:
    """Report where the authenticated user's queued gear or health sync is.

    ``Retry-After`` says when to poll again while the sync is not finished.
    """
    sync = garmin_sync_service.get_sync_status(token_user_id, kind, sync_states)
    core_location.set_retry_after_while_running(response, sync.status, garmin_constants.SYNC_POLL_SECONDS)
    return sync


@router.delete(
    "/link",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def garminconnect_unlink(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Unlink the user's Garmin Connect account."""
    garmin_service.unlink_account(token_user_id, db)
