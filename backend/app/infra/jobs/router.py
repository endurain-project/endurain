"""HTTP routes for the durable-jobs admin dashboard (admin only)."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import infra.jobs.crud as jobs_crud
import infra.jobs.schema as jobs_schema
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/summary",
    response_model=jobs_schema.JobsSummary,
    status_code=status.HTTP_200_OK,
)
def read_jobs_summary(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> jobs_schema.JobsSummary:
    """
    Get the durable-jobs processing summary for the admin dashboard.

    Requires admin authentication with the server_settings:read scope.

    Args:
        hours: Look-back window in hours (1-168) for the status/subscriber counts.
        db: Active database session.

    Returns:
        Window counts, per-subscriber breakdown, oldest pending age, and the
        current dead-letter queue.
    """
    return jobs_crud.get_jobs_summary(db, hours=hours)


@router.post(
    "/{job_id}/replay",
    response_model=jobs_schema.JobReplayResult,
    status_code=status.HTTP_200_OK,
)
def replay_dead_letter_job(
    job_id: str,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> jobs_schema.JobReplayResult:
    """
    Requeue a dead-lettered job for a fresh run.

    Requires admin authentication with the server_settings:write scope. Returns
    404 when no dead-letter job has the given id.

    Args:
        job_id: The job to replay.
        db: Active database session.

    Returns:
        The replay result.
    """
    replayed = jobs_crud.replay_dead_letter_job(job_id, now=datetime.now(UTC), db=db)
    if not replayed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No dead-letter job with that id",
        )
    return jobs_schema.JobReplayResult(replayed=True)
