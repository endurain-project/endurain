"""HTTP routes for the durable-jobs admin dashboard (admin only)."""

from collections.abc import Callable
from typing import Annotated

import jasil.admin as jasil_admin
from fastapi import APIRouter, HTTPException, Query, Security, status

import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/summary",
    response_model=jasil_admin.JobsSummary,
    status_code=status.HTTP_200_OK,
)
def read_jobs_summary(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> jasil_admin.JobsSummary:
    """
    Get the durable-jobs processing summary for the admin dashboard.

    Requires admin authentication with the server_settings:read scope. The
    aggregate opens its own short-lived session rather than taking this
    request's, so the read can never commit work the request left uncommitted.

    Args:
        hours: Look-back window in hours (1-168) for the status/subscriber counts.

    Returns:
        Window counts, per-subscriber breakdown, oldest pending age, and the
        current dead-letter queue.
    """
    return jasil_admin.get_jobs_summary(hours=hours)


@router.post(
    "/{job_id}/replay",
    response_model=jasil_admin.JobReplayResult,
    status_code=status.HTTP_200_OK,
)
def replay_dead_letter_job(
    job_id: str,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
) -> jasil_admin.JobReplayResult:
    """
    Requeue a dead-lettered job for a fresh run.

    Requires admin authentication with the server_settings:write scope. Returns
    404 when no dead-letter job has the given id.

    Args:
        job_id: The job to replay.

    Returns:
        The replay result.
    """
    result = jasil_admin.replay_dead_letter_job(job_id)
    if not result.replayed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No dead-letter job with that id",
        )
    return result
