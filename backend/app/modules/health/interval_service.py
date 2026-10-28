"""Resolve a list request's interval against the user's own calendar."""

from datetime import date

from sqlalchemy.orm import Session

import modules.health.computation as health_computation
import modules.health.constants as health_constants
import modules.users.users.integration_service as users_integration


def interval_start(user_id: int, interval: health_constants.Interval | None, db: Session) -> date | None:
    """Return the first date of an interval in the user's own calendar, or ``None``.

    Args:
        user_id: The user whose "today" anchors the interval.
        interval: The interval to resolve.
        db: Database session.

    Returns:
        The interval's start date, or ``None`` when no interval is given.
    """
    if interval is None:
        return None
    return health_computation.get_start_date_for_interval(interval.value, users_integration.local_today(user_id, db))
