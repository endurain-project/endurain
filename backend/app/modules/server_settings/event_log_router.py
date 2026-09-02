"""HTTP route for the event_log observability dashboard (admin only)."""

from collections.abc import Callable
from typing import Annotated

import jasil.admin as jasil_admin
from fastapi import APIRouter, Query, Security, status

import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/summary",
    response_model=jasil_admin.EventLogSummary,
    status_code=status.HTTP_200_OK,
)
def read_event_log_summary(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> jasil_admin.EventLogSummary:
    """
    Get aggregated event-processing observability for the admin dashboard.

    Requires admin authentication with the server_settings:read scope. The
    aggregate opens its own short-lived session rather than taking this
    request's, so the read can never commit work the request left uncommitted.

    Args:
        hours: Look-back window in hours (1-168) for throughput/latency stats.

    Returns:
        Aggregated event_log summary — throughput, outcomes, latency, pending
        work, and the most recent failures.
    """
    return jasil_admin.get_event_log_summary(hours=hours)
