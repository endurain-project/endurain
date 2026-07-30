"""FastAPI routes for activity ingestion (file upload, bulk import, provider refresh).

These endpoints stay under the ``/activities`` prefix but live here (not in
``activity/router.py``) because they drive the format/provider-aware ingestion flows:
file parsing via :mod:`~modules.activities.activity_ingestion.upload_entry` and live
provider sync via the Strava/Garmin clients. Keeping them here leaves the activities
core router fully parser- and provider-agnostic (enforced by the import-linter contract
``activities-parsing-boundary``).
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.bulk_import_service as bulk_import_service
import modules.activities.activity_ingestion.ingestion_jobs as ingestion_jobs
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies

logger = core_logger.get_logger(__name__)

# Bulk import endpoint (JWT auth)
router = APIRouter()

# Separate router for upload endpoint that supports
# both JWT and API key authentication
api_upload_router = APIRouter()


@api_upload_router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJob,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_activity_with_uploaded_file(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_user_id_from_auth),
    ],
    file: UploadFile,
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_auth_scopes,
            scopes=["activities:upload"],
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            max_length=255,
            description=(
                "Optional client-generated key. Replaying a request with the same key returns "
                "the original job instead of importing the file again."
            ),
        ),
    ] = None,
) -> activity_ingestion_schema.ActivityIngestionJob:
    """
    Upload an activity file (GPX, FIT, TCX, GZ) for import.

    Returns ``202`` once the file is stored and queued: parsing is seconds of
    CPU work, and doing it inline held a shared request thread for the duration.
    Poll ``GET /activities/ingestion-jobs/{job_id}`` for the outcome.

    Rejections that can be decided cheaply — unsupported extension, failed
    signature check, oversized body — still come back synchronously as a 4xx, so
    only files that plausibly import get a job.

    Send an ``Idempotency-Key`` to make a retry safe: a client that never saw
    the 202 has no job id to poll, so replaying the upload is its only recovery,
    and without a key that replay would import the file a second time.

    Accepts both JWT bearer token and API key
    authentication (X-API-Key header or ?api_key=
    query parameter). Requires the
    ``activities:upload`` scope.

    Args:
        token_user_id: Authenticated user ID.
        file: The activity file to upload.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.
        idempotency_key: Optional key identifying this request.

    Returns:
        The accepted upload job, in the pending state.
    """
    return ingestion_jobs.accept_upload(token_user_id, file, db, idempotency_key=idempotency_key)


@api_upload_router.get(
    "/ingestion-jobs/{job_id}",
    status_code=200,
    response_model=activity_ingestion_schema.ActivityIngestionJob,
)
def get_activity_ingestion_job(
    job_id: str,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_user_id_from_auth),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_auth_scopes,
            scopes=["activities:upload"],
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_ingestion_schema.ActivityIngestionJob:
    """
    Read the state of one of your ingestion requests.

    Serves both uploads and provider refreshes: the caller's question is the
    same either way, so there is one route rather than two near-identical ones.

    Scoped to the caller: a job belonging to another user is reported as not
    found rather than forbidden, so the endpoint does not confirm that an id
    exists.

    Args:
        job_id: The job identifier returned by the upload or refresh route.
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        The ingestion job.

    Raises:
        NotFoundError: If no such job belongs to the caller.
    """
    return ingestion_jobs.get_job(job_id, token_user_id, db)


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activities_schema.ActivityMessageResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_activity_with_bulk_import(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> activities_schema.ActivityMessageResponse:
    """Queue every importable file in the caller's bulk-import directory.

    Returns ``202``: the files are validated and queued in the request, but
    parsing them happens on a background worker.

    Args:
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        A message describing how many files were queued.

    Raises:
        ProcessingError: If the directory cannot be read or the jobs cannot be
            queued.
    """
    queued = bulk_import_service.start_bulk_import(token_user_id, db)
    return activities_schema.ActivityMessageResponse(
        detail=(
            f"Bulk import initiated for {queued} file(s) found in the "
            "bulk_import directory. Processing of files will continue in the background."
        )
    )


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJob,
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def refresh_activities(
    request: Request,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_ingestion_schema.ActivityIngestionJob:
    """Queue a sync of the last 24h from the linked providers (Strava/Garmin).

    Returns ``202`` with a job handle; poll
    ``GET /activities/ingestion-jobs/{job_id}`` for the outcome.

    This used to be the one ``async def`` route in activities, awaiting the
    provider clients inline. Everything synchronous on those paths — the
    integration lookups, the per-activity dedup reads — therefore ran on the
    event loop, where they stall every other request in the process instead of
    occupying a single worker thread. Running the sync as a job removes that
    class of bug rather than auditing for it: no provider code touches the loop
    any more.

    Args:
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        The accepted refresh job, in the pending state.
    """
    return ingestion_jobs.accept_refresh(token_user_id, db)
