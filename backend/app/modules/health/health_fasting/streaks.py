"""Fasting streak arithmetic."""

from datetime import date, timedelta
from itertools import pairwise


def calculate_streaks(completed_dates: list[date], today: date) -> tuple[int, int]:
    """Return the current and longest runs of consecutive days with a completed fast.

    The current streak only counts when the latest fast was today or yesterday.
    ``today`` is the athlete's own, in the same timezone the dates were bucketed
    in; comparing against the server's local today would mix two day definitions.

    Args:
        completed_dates: Distinct dates with a completed fast, sorted ascending.
        today: The athlete's current calendar date.

    Returns:
        Tuple of (current_streak, longest_streak).
    """
    if not completed_dates:
        return 0, 0

    one_day = timedelta(days=1)

    # Single forward pass: track the longest run of consecutive days while
    # leaving `run` holding the streak length ending on the most recent date.
    longest_streak = 1
    run = 1
    for previous, current in pairwise(completed_dates):
        run = run + 1 if current - previous == one_day else 1
        longest_streak = max(longest_streak, run)

    current_streak = run if completed_dates[-1] in (today, today - one_day) else 0

    return current_streak, longest_streak
