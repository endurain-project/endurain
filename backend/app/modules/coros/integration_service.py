"""The COROS surface consumed by other modules."""

import uuid
from datetime import datetime

import jasil.runtime as platform_runtime
from sqlalchemy.orm import Session

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.coros.activity_service as coros_activity_service
import modules.coros.constants as coros_constants
import modules.coros.crud as coros_crud
from core.database import SessionLocal


def _fetch_window(
    user_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store a user's COROS activities recorded in the given window.

    Args:
        user_id: The user whose COROS account to pull from.
        window_start: Inclusive start of the window.
        window_end: Inclusive end of the window.

    Returns:
        The stored activities, or None when COROS is not linked.
    """
    return coros_activity_service.get_user_coros_activities_by_dates(
        platform_runtime.get_active_platform(),
        window_start,
        window_end,
        user_id,
    )


def _linked_user_ids(after_id: uuid.UUID | None, limit: int) -> list[uuid.UUID]:
    """Page through the users who have linked COROS.

    Args:
        after_id: Return only users with an id greater than this, or ``None`` from the first page.
        limit: Maximum number of user ids to return.

    Returns:
        The linked user ids, ascending.
    """
    with SessionLocal() as db:
        return coros_crud.list_linked_user_ids(after_id, limit, db)


def is_linked(user_id: uuid.UUID, db: Session) -> bool:
    """Return whether a user has a connected COROS account.

    Args:
        user_id: User to check.
        db: Database session.

    Returns:
        True when a COROS access token is stored for the user.
    """
    return coros_crud.is_linked(user_id, db)


def register_activity_provider() -> None:
    """Register COROS with the activity-ingestion provider registry."""
    activity_ingestion_integration.register_activity_provider(
        coros_constants.PROVIDER_NAME,
        _fetch_window,
        _linked_user_ids,
    )
