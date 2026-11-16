"""COROS integration routes."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import APIRouter, Depends, Request, Security
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.coros.constants as coros_constants
import modules.coros.oauth as coros_oauth
import modules.coros.provider_registry as coros_provider_registry
import modules.coros.schema as coros_schema
import modules.coros.service as coros_service

logger = core_logger.get_logger(__name__)

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
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def coros_authorize(
    request: Request,
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> coros_schema.CorosAuthorizeRead:
    """Start the COROS OAuth authorization for the caller."""
    try:
        url = coros_service.begin_authorization(token_user_id, _redirect_uri(), db)
    except coros_oauth.CorosOAuthError as err:
        logger.error(
            "Unable to start the COROS authorization",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
        raise core_exceptions.UpstreamError("Unable to connect to COROS") from err
    return coros_schema.CorosAuthorizeRead(authorization_url=url)


@router.put("/link")
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def coros_link(
    request: Request,
    payload: coros_schema.CorosLinkRequest,
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[platform_providers.StorageProvider, Depends(core_dependencies.get_storage)],
) -> dict:
    """Finish the COROS OAuth callback and queue the initial sync."""
    try:
        coros_service.complete_link(token_user_id, payload.code, payload.state, db)
    except core_exceptions.InvalidInputError:
        raise
    except coros_oauth.CorosOAuthError as err:
        logger.error(
            "Unable to link the COROS account",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
        raise core_exceptions.UpstreamError("Unable to link the COROS account") from err

    try:
        end = datetime.now(UTC)
        activity_ingestion_integration.request_provider_sync(
            token_user_id,
            coros_provider_registry.PROVIDER_NAME,
            end - timedelta(days=coros_constants.INITIAL_SYNC_DAYS),
            end,
            storage,
            db,
        )
    except Exception as err:
        logger.error(
            "COROS linked but the initial sync could not be queued",
            exc_info=err,
            extra=core_logger.context(user_id=token_user_id),
        )
    return {"detail": f"COROS linked for user {token_user_id} successfully"}


@router.get("/status", response_model=coros_schema.CorosStatusRead)
def coros_status(
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> coros_schema.CorosStatusRead:
    """Return the caller's COROS connection and last-sync state."""
    return coros_service.get_status(token_user_id, db)


@router.post(
    "/sync",
    status_code=202,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def coros_sync(
    request: Request,
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[platform_providers.StorageProvider, Depends(core_dependencies.get_storage)],
    start_date: date | None = None,
    end_date: date | None = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a COROS activity sync.

    With no dates, the last seven days are re-read. An explicit range lets a
    user backfill older history, one job at a time.
    """
    if (start_date is None) != (end_date is None):
        raise core_exceptions.InvalidInputError("start_date and end_date must be provided together")
    if not coros_service.get_status(token_user_id, db).linked:
        raise core_exceptions.ConflictError("COROS is not connected")

    now = datetime.now(UTC)
    if start_date is None or end_date is None:
        window_start = now - timedelta(days=coros_constants.MANUAL_SYNC_DAYS)
        window_end = now
    else:
        if start_date > end_date:
            raise core_exceptions.InvalidInputError("start_date must not be after end_date")
        if (end_date - start_date).days + 1 > coros_constants.MAX_MANUAL_SYNC_DAYS:
            raise core_exceptions.InvalidInputError(
                f"A COROS backfill is limited to {coros_constants.MAX_MANUAL_SYNC_DAYS} days"
            )
        window_start = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
        window_end = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)

    job = activity_ingestion_integration.request_provider_sync(
        token_user_id,
        coros_provider_registry.PROVIDER_NAME,
        window_start,
        window_end,
        storage,
        db,
    )
    logger.info("COROS activities queued for user", extra=core_logger.context(user_id=token_user_id))
    return job


@router.delete("/unlink")
def coros_unlink(
    _validate_access_token: Annotated[Callable, Depends(auth_dependencies.validate_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> dict:
    """Revoke COROS access when possible and clear the local connection."""
    coros_service.unlink(token_user_id, db)
    return {"detail": f"COROS unlinked for user {token_user_id} successfully"}
