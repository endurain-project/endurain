"""API routes that read background jobs, served under ``/jobs``."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, Security

import core.dependencies as core_dependencies
import core.job_status as core_job_status
import core.location as core_location
import core.pagination as core_pagination
import modules.auth.dependencies as auth_dependencies
import modules.jobs.schema as jobs_schema
import modules.jobs.service as jobs_service

router = APIRouter()


@router.get(
    "",
    response_model=jobs_schema.JobPage,
    # No scope of its own: the scope a job needs depends on its kind, so the handler checks it.
    dependencies=[Security(auth_dependencies.check_scopes, scopes=[])],
)
def list_jobs(
    caller: auth_dependencies.CurrentPrincipal,
    state: core_dependencies.PlatformState,
    db: core_dependencies.DbSession,
    kind: Annotated[jobs_schema.JobKind | None, Query()] = None,
    status: Annotated[core_job_status.JobState | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> jobs_schema.JobPage:
    """List a keyset slice of the background jobs the caller started, newest first.

    Only the kinds the caller's scopes allow are listed, so an API key with ``activities:upload`` sees its
    uploads and imports alone. A job other than an activity upload, refresh or bulk import is listed while its
    record lasts, which is minutes to hours after it finishes.
    """
    return jobs_service.list_jobs(
        caller.user_id,
        caller.scopes,
        state,
        db,
        kind=kind,
        status=status,
        cursor=cursor,
        num_records=num_records or core_pagination.DEFAULT_NUM_RECORDS,
    )


@router.get(
    "/{job_id}",
    name=core_job_status.JOB_ROUTE,
    response_model=jobs_schema.JobRead,
    responses={200: {"headers": core_location.POLLED_STATUS_HEADERS}},
    # No scope of its own: the scope a job needs depends on its kind, so the handler checks it.
    dependencies=[Security(auth_dependencies.check_scopes, scopes=[])],
)
def read_job(
    job_id: Annotated[str, Path(min_length=1, max_length=64)],
    caller: auth_dependencies.CurrentPrincipal,
    state: core_dependencies.PlatformState,
    db: core_dependencies.DbSession,
    response: Response,
) -> jobs_schema.JobRead:
    """Report where a background job is.

    ``kind`` says what the job does and which fields it carries. ``Retry-After`` says when to poll again while
    the job is not finished. A job the caller did not start, or one whose record has expired, is ``404``; an
    account deletion is also readable by any holder of ``users:read-all``. Reading a job needs the scope its kind
    asks for: ``activities:upload`` for an activity upload, refresh or bulk import, ``activities:read`` for a bulk
    edit, ``account:integrations`` for a Garmin Connect link or a Strava link or unlink, ``account`` for a Garmin
    Connect or Strava gear or health sync, ``account:export`` for a profile export or import and
    ``users:read-all`` for an account deletion.
    """
    view = jobs_service.get_job(job_id, caller.user_id, caller.scopes, state, db)
    auth_dependencies.require_scopes(caller.scopes, view.scope)
    core_location.set_retry_after_while_running(response, view.job.status, view.poll_seconds)
    return view.job
