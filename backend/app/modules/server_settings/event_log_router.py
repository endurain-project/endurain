"""HTTP route for the event_log observability dashboard (admin only)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import infra.event_log.crud as event_log_crud
import infra.event_log.schema as event_log_schema
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/summary",
    response_model=event_log_schema.EventLogSummary,
    status_code=status.HTTP_200_OK,
)
def read_event_log_summary(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> event_log_schema.EventLogSummary:
    """
    Get aggregated event-processing observability for the admin dashboard.

    Requires admin authentication with the server_settings:read scope.

    Args:
        hours: Look-back window in hours (1-168) for throughput/latency stats.
        db: Active database session.

    Returns:
        Aggregated event_log summary — throughput, outcomes, latency, pending
        work, and the most recent failures.
    """
    return event_log_crud.get_event_log_summary(db, hours=hours)
