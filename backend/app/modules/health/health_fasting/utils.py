from datetime import date, timedelta
from itertools import pairwise

from sqlalchemy.orm import Session

import modules.health.health_fasting.crud as health_fasting_crud


def calculate_streaks(user_id: int, db: Session) -> tuple[int, int]:
    """
    Calculate current and longest fasting streaks.

    Args:
        user_id: User ID to calculate streaks for.
        db: Database session.

    Returns:
        Tuple of (current_streak, longest_streak).
    """
    # Distinct completed-fast dates, sorted ascending, straight from SQL.
    dates = health_fasting_crud.get_completed_fasting_dates_by_user_id(user_id, db)

    if not dates:
        return 0, 0

    one_day = timedelta(days=1)

    # Single forward pass: track the longest run of consecutive days while
    # leaving `run` holding the streak length ending on the most recent date.
    longest_streak = 1
    run = 1
    for previous, current in pairwise(dates):
        run = run + 1 if current - previous == one_day else 1
        longest_streak = max(longest_streak, run)

    # The current streak only counts if the latest fast was today or yesterday.
    today = date.today()
    current_streak = run if dates[-1] in (today, today - one_day) else 0

    return current_streak, longest_streak
