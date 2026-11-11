"""FastAPI routes for activity ingestion (file upload, bulk import, provider refresh).

These endpoints stay under the ``/activities`` prefix but live here (not in
``activity/router.py``) because they drive the format/provider-aware ingestion flows:
file parsing via :mod:`~modules.activities.activity_ingestion.upload_entry_service` and live
provider sync via the Strava/Garmin clients. Keeping them here leaves the activities
core router fully parser- and provider-agnostic (enforced by the import-linter contract
``activities-parsing-boundary``).
"""

from functools import partial
from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
    Request,
    Response,
    Security,
    UploadFile,
    status,
)

import core.dependencies as core_dependencies
import core.file_uploads as core_file_uploads
import core.location as core_location
import core.middleware_body_limit as core_middleware_body_limit
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.bulk_import_service as activity_ingestion_bulk_import_service
import modules.activities.activity_ingestion.dependencies as activity_ingestion_dependencies
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.service as activity_ingestion_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:upload"])],
    openapi_extra=core_middleware_body_limit.upload_limit(
        max(
            core_file_uploads.max_bytes_for(core_file_uploads.UploadKind.ACTIVITY),
            core_file_uploads.max_bytes_for(core_file_uploads.UploadKind.GZIP),
        )
    ),
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_activity_with_uploaded_file(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    file: UploadFile,
    response: Response,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
    idempotency_key: activity_ingestion_dependencies.IdempotencyKey = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Upload an activity file (GPX, FIT, TCX, GZ) for import.

    Returns ``202`` once the file is stored and queued: parsing is seconds of
    CPU work, and doing it inline held a shared request thread for the duration.
    Poll ``GET /jobs/{job_id}`` for the outcome; ``Content-Location`` names it and
    ``Retry-After`` says when to look first.

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
    """
    job = activity_ingestion_service.accept_upload(
        token_user_id,
        file.filename,
        partial(core_file_uploads.save_validated_upload_sync, file),
        storage,
        db,
        idempotency_key=idempotency_key,
    )
    activity_ingestion_integration.set_job_location(response, request, job)
    return job


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    openapi_extra=core_middleware_body_limit.upload_limit(
        core_file_uploads.max_bytes_for(core_file_uploads.UploadKind.ZIP)
    ),
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_bulk_import_from_archive(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    file: UploadFile,
    response: Response,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
    source: Annotated[
        str,
        Query(
            max_length=50,
            description=(
                "The archive layout: `generic` for plain activity files, or a provider export such as `strava`."
            ),
        ),
    ] = activity_ingestion_bulk_import_service.GENERIC_FORMAT_NAME,
    idempotency_key: activity_ingestion_dependencies.IdempotencyKey = None,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Import every activity file in an uploaded ZIP archive.

    Returns ``202`` once the archive is stored and queued: nothing inside it is
    read in the request beyond its directory listing. Poll
    ``GET /jobs/{job_id}`` for progress (``files_done`` and
    ``files_failed`` against ``files_total``); a finished import with failed files
    still ends ``completed``.

    One bulk import runs per user at a time; a second request while one is running
    is answered ``409`` with the running job's ``job_id`` and a ``Content-Location`` naming it.

    Send an ``Idempotency-Key`` to make a retry safe: a repeat of the same archive and ``source`` returns the
    original job instead of starting another, and the same key with a different archive is ``409``.
    """
    job = activity_ingestion_bulk_import_service.accept_archive(
        token_user_id,
        file.filename,
        partial(core_file_uploads.save_validated_upload_sync, file),
        source,
        storage,
        db,
        idempotency_key=idempotency_key,
    )
    activity_ingestion_integration.set_job_location(response, request, job)
    return job


@router.post(
    "/bulk-import/folder",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_bulk_import_from_folder(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    response: Response,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
    source: Annotated[
        str,
        Query(
            max_length=50,
            description="The folder layout: `generic` for plain activity files, or a provider export such as `strava`.",
        ),
    ] = activity_ingestion_bulk_import_service.GENERIC_FORMAT_NAME,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Import the files in the caller's folder on the server.

    The folder is per user (`bulk_import/<user_id>` for plain files, or the
    provider export's own per-user folder). Returns ``202`` with a job handle;
    packing and staging the folder happens in the background, and the files are
    removed from the folder only once they are safely staged. Poll
    ``GET /jobs/{job_id}`` for progress.

    One bulk import runs per user at a time; a second request while one is running
    is answered ``409`` with the running job's ``job_id`` and a ``Content-Location`` naming it.
    """
    job = activity_ingestion_bulk_import_service.start_from_directory(token_user_id, source, storage, db)
    activity_ingestion_integration.set_job_location(response, request, job)
    return job


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def refresh_activities(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    response: Response,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a sync of the last 24h from the linked providers (Strava/Garmin).

    Returns ``202`` with a job handle; poll
    ``GET /jobs/{job_id}`` for the outcome.

    The sync runs as a job, so no provider call blocks a request thread or the
    event loop.
    """
    job = activity_ingestion_service.accept_refresh(token_user_id, storage, db)
    activity_ingestion_integration.set_job_location(response, request, job)
    return job
