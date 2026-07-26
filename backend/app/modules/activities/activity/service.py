"""Application-layer orchestration for reading activities.

Thin sync routes delegate their read/stats/feed orchestration here: timeframe
math, owner-vs-requester scoping, aggregate stats, and the following-feed access
guard. Functions return schemas / DTOs / primitives and never expose ORM
instances. The only non-return side effect is raising ``HTTPException`` for
access-control failures — matching the module's established CRUD error
convention (a pure domain-exception boundary is a later refinement).
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.stats as activities_stats
import modules.followers.service as followers_service


def get_activities_in_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    requester_user_id: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Return a user's activities in ``[start, end]`` scoped to the requester.

    The owner sees all of their activities; any other requester sees only the
    ones visible to them (the CRUD layer applies the visibility mask).

    Args:
        user_id: The owner of the activities.
        start: Inclusive start of the window (timezone-aware UTC).
        end: Inclusive end of the window (timezone-aware UTC).
        requester_user_id: The authenticated user making the request.
        db: Database session.

    Returns:
        The scoped activities, or ``None`` when there are none.
    """
    is_owner = user_id == requester_user_id
    core_logger.print_to_log(
        f"get_activities_in_timeframe: user {user_id} "
        f"[{'owner' if is_owner else 'requester-scoped'}] window {start}..{end}",
        "debug",
    )
    if is_owner:
        return activities_crud.get_user_activities_per_timeframe(user_id, start, end, db, True)
    return activities_crud.get_user_activities_per_timeframe(
        user_id,
        start,
        end,
        db,
        False,
        requester_user_id=requester_user_id,
    )


def _anchor_date(anchor: date | None) -> datetime:
    """Return the midnight-aligned day the week/month window is built around.

    ``anchor`` is the *caller's* local calendar date. The request carries no
    timezone, so without it the server can only fall back to its own UTC date —
    which is the previous day for up to 13 hours at UTC+13 and the next day for
    up to 11 hours at UTC-11, putting "this week" and "this month" one period
    off around their boundaries.

    Args:
        anchor: The caller's local date, or ``None`` to fall back to the server's
            UTC date.

    Returns:
        A midnight-aligned UTC datetime for the anchor day.
    """
    if anchor is not None:
        return datetime.combine(anchor, time.min, tzinfo=UTC)
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _week_bounds(week_number: int = 0, anchor: date | None = None) -> tuple[datetime, datetime]:
    """Return the (start, end) of the week ``week_number`` weeks ago (0 = current).

    Both bounds are midnight-aligned so the window is a real calendar week
    (Monday 00:00 through Sunday, inclusive). They previously carried the current
    time of day, which made "this week" a rolling span anchored on *now* rather
    than on the week's boundaries.
    """
    today = _anchor_date(anchor)
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    return start_of_week, start_of_week + timedelta(days=6)


def _month_bounds(anchor: date | None = None) -> tuple[datetime, datetime]:
    """Return the (start, end) of the calendar month containing the anchor day.

    Midnight-aligned for the same reason as :func:`_week_bounds`: keeping the
    current time of day meant activities recorded on the 1st before "now" fell
    outside the month window.
    """
    today = _anchor_date(anchor)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(day=calendar.monthrange(today.year, today.month)[1])
    return start_of_month, end_of_month


def list_week_activities(
    user_id: int,
    week_number: int,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> list[activities_schema.Activity] | None:
    """List a user's activities for the week ``week_number`` weeks ago (0 = current)."""
    start, end = _week_bounds(week_number, anchor)
    return get_activities_in_timeframe(user_id, start, end, requester_user_id, db)


def week_stats(
    user_id: int,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's current-week activities."""
    start, end = _week_bounds(0, anchor)
    activities = get_activities_in_timeframe(user_id, start, end, requester_user_id, db)
    if activities:
        return activities_stats.calculate_activity_stats(activities)
    return activities_schema.ActivityStats()


def month_stats(
    user_id: int,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's current-month activities."""
    start, end = _month_bounds(anchor)
    activities = get_activities_in_timeframe(user_id, start, end, requester_user_id, db)
    if activities:
        return activities_stats.calculate_activity_stats(activities)
    return activities_schema.ActivityStats()


def count_month_activities(
    user_id: int,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> int:
    """Count a user's current-month activities (requester-scoped)."""
    start, end = _month_bounds(anchor)
    activities = get_activities_in_timeframe(user_id, start, end, requester_user_id, db)
    return len(activities) if activities else 0


def period_stats(
    user_id: int,
    period: str,
    requester_user_id: int,
    db: Session,
    anchor: date | None = None,
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's ``week`` or ``month`` (default week).

    Args:
        user_id: The user whose stats to aggregate.
        period: ``week`` or ``month``.
        requester_user_id: The authenticated user making the request.
        db: Database session.
        anchor: The caller's local calendar date, used to decide which week or
            month is "current". Falls back to the server's UTC date.
    """
    core_logger.print_to_log(
        f"period_stats: user {user_id} period={period!r} requester {requester_user_id} anchor={anchor}",
        "debug",
    )
    if period == "month":
        return month_stats(user_id, requester_user_id, db, anchor)
    return week_stats(user_id, requester_user_id, db, anchor)


def count_user_activities(
    user_id: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
) -> int:
    """Count a user's own activities matching the given filters."""
    return activities_crud.count_user_activities(
        user_id=user_id,
        db=db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
    )


def list_gear_activities(
    user_id: int,
    gear_id: int,
    page_number: int | None,
    num_records: int | None,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """List a user's activities for a gear (paginated when page/size are given)."""
    if page_number is not None and num_records is not None:
        return activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
            user_id, gear_id, page_number, num_records, db
        )
    return activities_crud.get_user_activities_by_gear_id_and_user_id(user_id, gear_id, db)


def count_gear_activities(user_id: int, gear_id: int, db: Session) -> int:
    """Count a user's activities for a gear."""
    return activities_crud.get_gear_activities_count_by_user_id(user_id, gear_id, db)


def list_user_activities_paginated(
    user_id: int,
    requester_user_id: int,
    page_number: int,
    num_records: int,
    db: Session,
    *,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
) -> list[activities_schema.Activity] | None:
    """List a user's activities (filtered, paginated) scoped to the requester.

    The owner sees all of their activities; any other requester sees only the
    ones visible to them (the CRUD layer applies the mask from ``user_is_owner``
    plus the requester id).
    """
    activities = activities_crud.get_user_activities_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
        user_is_owner=(user_id == requester_user_id),
        requester_user_id=requester_user_id,
    )
    core_logger.print_to_log(
        f"list_user_activities_paginated: user {user_id} requester {requester_user_id} "
        f"page {page_number} size {num_records} -> {len(activities) if activities else 0} activities",
        "debug",
    )
    return activities


def _require_feed_owner(user_id: int, requester_user_id: int) -> None:
    """Enforce that the requester is reading their own following feed (OWASP A01 / IDOR)."""
    if user_id != requester_user_id:
        core_logger.print_to_log(
            f"Blocked following-feed access: user {requester_user_id} requested the feed of user {user_id}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


def get_following_feed(
    user_id: int,
    requester_user_id: int,
    page_number: int,
    num_records: int,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """Return the requester's following feed (activities of users they follow)."""
    _require_feed_owner(user_id, requester_user_id)
    followee_ids = followers_service.list_accepted_followee_ids(requester_user_id, db)
    feed = activities_crud.get_user_following_activities_with_pagination(followee_ids, page_number, num_records, db)
    core_logger.print_to_log(
        f"get_following_feed: user {requester_user_id} page {page_number} -> {len(feed) if feed else 0} activities",
        "debug",
    )
    return feed


def count_following_feed(user_id: int, requester_user_id: int, db: Session) -> int:
    """Count the requester's following-feed activities."""
    _require_feed_owner(user_id, requester_user_id)
    followee_ids = followers_service.list_accepted_followee_ids(requester_user_id, db)
    return activities_crud.count_user_following_activities(followee_ids, db)
