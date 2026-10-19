"""FastAPI routes for activity ingestion (file upload, bulk import, provider refresh).

These endpoints stay under the ``/activities`` prefix but live here (not in
``activity/router.py``) because they drive the format/provider-aware ingestion flows:
file parsing via :mod:`~modules.activities.activity_ingestion.upload_entry_service` and live
provider sync via the Strava/Garmin clients. Keeping them here leaves the activities
core router fully parser- and provider-agnostic (enforced by the import-linter contract
``activities-parsing-boundary``).
"""

from collections.abc import Callable
from functools import partial
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    Request,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.file_uploads as core_file_uploads
import core.rate_limit as core_rate_limit
import modules.activities.activity_ingestion.bulk_import_service as activity_ingestion_bulk_import_service
import modules.activities.activity_ingestion.dependencies as activity_ingestion_dependencies
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.service as activity_ingestion_service
import modules.auth.dependencies as auth_dependencies

# Bulk import endpoint (JWT auth)
router = APIRouter()

# Separate router for upload endpoint that supports
# both JWT and API key authentication
api_upload_router = APIRouter()


@api_upload_router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
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
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
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
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Upload an activity file (GPX, FIT, TCX, GZ) for import.

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
    """
    return activity_ingestion_service.accept_upload(
        token_user_id,
        file.filename,
        partial(core_file_uploads.save_validated_upload_sync, file),
        storage,
        db,
        idempotency_key=idempotency_key,
    )


@api_upload_router.get(
    "/ingestion-jobs/{job_id}",
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
)
def read_activity_ingestion_job(
    job_id: activity_ingestion_dependencies.JobId,
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
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Read the state of one of your ingestion requests.

    Serves both uploads and provider refreshes: the caller's question is the
    same either way, so there is one route rather than two near-identical ones.

    Scoped to the caller: a job belonging to another user is reported as not
    found rather than forbidden, so the endpoint does not confirm that an id
    exists.
    """
    return activity_ingestion_service.get_job(job_id, token_user_id, db)


@router.post(
    "/bulk-import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_bulk_import_from_archive(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    file: UploadFile,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
    source: Annotated[
        str,
        Query(
            max_length=50,
            description="The archive layout: `generic` for plain activity files, or a provider export such as `strava`.",
        ),
    ] = activity_ingestion_bulk_import_service.GENERIC_FORMAT_NAME,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Import every activity file in an uploaded ZIP archive.

    Returns ``202`` once the archive is stored and queued: nothing inside it is
    read in the request beyond its directory listing. Poll
    ``GET /activities/ingestion-jobs/{job_id}`` for progress (``files_done`` and
    ``files_failed`` against ``files_total``); a finished import with failed files
    still ends ``completed``.

    One bulk import runs per user at a time; a second request while one is running
    is answered ``409``.
    """
    return activity_ingestion_bulk_import_service.accept_archive(
        token_user_id,
        file.filename,
        partial(core_file_uploads.save_validated_upload_sync, file),
        source,
        storage,
        db,
    )


@router.post(
    "/bulk-import/folder",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def create_bulk_import_from_folder(
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
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
    ``GET /activities/ingestion-jobs/{job_id}`` for progress.

    One bulk import runs per user at a time; a second request while one is running
    is answered ``409``.
    """
    return activity_ingestion_bulk_import_service.start_from_directory(token_user_id, source, storage, db)


@router.post(
    "/refresh",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
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
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a sync of the last 24h from the linked providers (Strava/Garmin).

    Returns ``202`` with a job handle; poll
    ``GET /activities/ingestion-jobs/{job_id}`` for the outcome.

    The sync runs as a job, so no provider call blocks a request thread or the
    event loop.
    """
    return activity_ingestion_service.accept_refresh(token_user_id, storage, db)
