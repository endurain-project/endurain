"""COROS integration routes."""

from datetime import date

from fastapi import APIRouter, Request, Response, Security, status

import core.config as core_config
import core.date_range as core_date_range
import core.dependencies as core_dependencies
import core.location as core_location
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema
import modules.coros.schema as coros_schema
import modules.coros.service as coros_service

router = APIRouter()

_CALLBACK_PATH = "/coros/callback"


def _redirect_uri() -> str:
    """Return the callback URI registered with COROS.

    Returns:
        The absolute URL of the frontend callback route.
    """
    return f"{core_config.settings.ENDURAIN_HOST.rstrip('/')}{_CALLBACK_PATH}"


@router.post(
    "/authorize",
    response_model=coros_schema.CorosAuthorizeRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:integrations"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def coros_authorize(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> coros_schema.CorosAuthorizeRead:
    """Start the COROS OAuth authorization for the caller."""
    return coros_schema.CorosAuthorizeRead(
        authorization_url=coros_service.begin_authorization(token_user_id, _redirect_uri(), db)
    )


@router.post(
    "/link",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:integrations"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def coros_link(
    request: Request,
    payload: coros_schema.CorosLinkRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> None:
    """Finish the COROS OAuth callback and queue the initial sync."""
    coros_service.complete_link(token_user_id, payload.code, payload.state, db)
    coros_service.request_initial_sync(token_user_id, storage, db)


@router.get(
    "/status",
    response_model=coros_schema.CorosStatusRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:integrations"])],
)
def coros_status(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> coros_schema.CorosStatusRead:
    """Return the caller's COROS connection and last-sync state."""
    return coros_service.get_status(token_user_id, db)


@router.post(
    "/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def coros_sync(
    request: Request,
    response: Response,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
    start_date: date | None = None,
    end_date: date | None = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a COROS activity sync.

    With no dates, the last seven days are re-read. An explicit range lets a
    user backfill older history, one job at a time.
    """
    core_date_range.refuse_reversed_range(start_date, end_date)
    job = coros_service.request_sync(token_user_id, start_date, end_date, storage, db)
    core_location.set_job_location(
        response,
        request,
        job.id,
        activity_ingestion_constants.job_poll_seconds(job.kind),
    )
    return job


@router.post(
    "/unlink",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account:integrations"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def coros_unlink(
    request: Request,
    body: auth_schema.StepUpRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    verify_step_up: auth_dependencies.StepUpVerifierDep,
    db: core_dependencies.DbSession,
) -> None:
    """Revoke COROS access when possible and clear the local connection."""
    coros_service.unlink(token_user_id, body.step_up, verify_step_up, db)
