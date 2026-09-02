"""CRUD operations for activity summary aggregations.

Every bucket (day / week / month / year) is derived from the activity's **local**
wall clock rather than the UTC value stored in the column — see
:mod:`modules.activities.activity.query`, which owns that rule for every query
over the activities table.

Named ``summary_crud`` rather than ``summary_query``: it opens a ``Session`` and
executes, which is the ``crud`` role, and the enforcement rules match on the
role. Under the old name it was the one persistence module in the tree that no
``modules.activities.*.crud`` contract and no logging-layer rule could see.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, extract, func, select
from sqlalchemy.orm import Session

import core.calendar as core_calendar
import core.logger as core_logger
from modules.activities.activity.constants import (
    ACTIVITY_NAME_TO_ID,
    set_activity_name_based_on_activity_type,
)
from modules.activities.activity.models import Activity
from modules.activities.activity.query import (
    local_date_range_conditions,
    local_start_time_expression,
)
from modules.activities.activity.summary_schema import (
    DaySummary,
    LifetimeSummaryResponse,
    MonthlySummaryResponse,
    MonthSummary,
    SummaryMetrics,
    TypeBreakdownItem,
    WeeklySummaryResponse,
    WeekSummary,
    YearlyPeriodSummary,
    YearlySummaryResponse,
)

logger = core_logger.get_logger(__name__)


def _apply_activity_type_filter(
    stmt: Select[Any],
    activity_type: str | None,
) -> tuple[Select[Any], int | None]:
    """
    Apply activity type name filter to a statement.

    Args:
        stmt: SQLAlchemy select statement.
        activity_type: Optional activity type name.

    Returns:
        Tuple of filtered statement and resolved
        type ID (or None).
    """
    if not activity_type:
        return stmt, None
    type_id = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
    if type_id is not None:
        return (
            stmt.where(Activity.activity_type == type_id),
            type_id,
        )
    # Unknown type - force empty result set
    return stmt.where(Activity.id == -1), None


def _get_type_breakdown(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    activity_type: str | None = None,
) -> list[TypeBreakdownItem]:
    """
    Get summary breakdown by activity type.

    Args:
        db: Database session.
        user_id: Target user ID.
        start_date: Period start (inclusive).
        end_date: Period end (exclusive).
        activity_type: Optional type name filter.

    Returns:
        List of per-type breakdown items.
    """
    stmt = select(
        Activity.activity_type.label("activity_type"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(
            func.sum(Activity.total_timer_time),
            0.0,
        ).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label("total_elevation_gain"),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).where(Activity.user_id == user_id)

    is_unbounded = start_date == date.min and end_date == date.max
    if not is_unbounded:
        stmt = stmt.where(*local_date_range_conditions(start_date, end_date, end_exclusive=True))

    if activity_type:
        type_id = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
        if type_id is not None:
            stmt = stmt.where(Activity.activity_type == type_id)
        else:
            return []

    stmt = stmt.group_by(Activity.activity_type).order_by(
        func.count(Activity.id).desc(),
        Activity.activity_type.asc(),
    )

    rows = db.execute(stmt).all()
    breakdown: list[TypeBreakdownItem] = []
    for row in rows:
        name = set_activity_name_based_on_activity_type(row.activity_type)
        breakdown.append(
            TypeBreakdownItem(
                activity_type_id=int(row.activity_type),
                activity_type=name,
                total_distance=float(row.total_distance),
                total_duration=float(row.total_duration),
                total_elevation_gain=float(row.total_elevation_gain),
                total_calories=float(row.total_calories),
                activity_count=int(row.activity_count),
            )
        )
    return breakdown


def get_weekly_summary(
    db: Session,
    user_id: int,
    target_date: date,
    first_day_of_week: core_calendar.WeekdayValue,
    activity_type: str | None = None,
) -> WeeklySummaryResponse:
    """
    Get weekly activity summary for a user.

    Args:
        db: Database session.
        user_id: Target user ID.
        target_date: Any date within the target
            week.
        first_day_of_week: User's configured first weekday.
        activity_type: Optional activity type
            filter name.

    Returns:
        Weekly summary with daily breakdowns.
    """
    first_day_index = core_calendar.get_weekday_index(first_day_of_week)
    start_of_week = core_calendar.get_week_start(target_date, first_day_of_week)
    end_of_week = start_of_week + timedelta(days=7)

    local_start_time = local_start_time_expression()

    # ISO day of week (1-7, Mon-Sun) evaluated on the activity's LOCAL wall clock
    # so a ride lands on the day the athlete rode it.
    iso_dow: ColumnElement[Any] = extract("isodow", local_start_time)

    stmt = select(
        iso_dow.label("day_of_week"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(
            func.sum(Activity.total_timer_time),
            0.0,
        ).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label("total_elevation_gain"),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).where(
        Activity.user_id == user_id,
        *local_date_range_conditions(start_of_week, end_of_week, end_exclusive=True),
    )

    stmt, _ = _apply_activity_type_filter(stmt, activity_type)

    stmt = stmt.group_by(iso_dow).order_by(iso_dow)

    daily_results = db.execute(stmt).all()
    breakdown: list[DaySummary] = []
    overall = SummaryMetrics()

    day_map = {d.day_of_week: d for d in daily_results}

    for day_offset in range(7):
        day_index = (first_day_index + day_offset) % 7
        iso_day_index = day_index + 1
        day_data = day_map.get(iso_day_index)
        if day_data:
            ds = DaySummary(
                day_of_week=day_index,
                total_distance=float(day_data.total_distance),
                total_duration=float(day_data.total_duration),
                total_elevation_gain=float(day_data.total_elevation_gain),
                total_calories=float(day_data.total_calories),
                activity_count=int(day_data.activity_count),
            )
            breakdown.append(ds)
            overall.total_distance += ds.total_distance
            overall.total_duration += ds.total_duration
            overall.total_elevation_gain += ds.total_elevation_gain
            overall.total_calories += ds.total_calories
            overall.activity_count += ds.activity_count
        else:
            breakdown.append(DaySummary(day_of_week=day_index))

    return WeeklySummaryResponse(
        total_distance=overall.total_distance,
        total_duration=overall.total_duration,
        total_elevation_gain=(overall.total_elevation_gain),
        total_calories=overall.total_calories,
        activity_count=overall.activity_count,
        breakdown=breakdown,
        type_breakdown=_get_type_breakdown(
            db,
            user_id,
            start_of_week,
            end_of_week,
            activity_type,
        ),
    )


def get_monthly_summary(
    db: Session,
    user_id: int,
    target_date: date,
    first_day_of_week: core_calendar.WeekdayValue,
    activity_type: str | None = None,
) -> MonthlySummaryResponse:
    """
    Get monthly activity summary for a user.

    Args:
        db: Database session.
        user_id: Target user ID.
        target_date: Any date within the target
            month.
        first_day_of_week: User's configured first weekday.
        activity_type: Optional activity type
            filter name.

    Returns:
        Monthly summary with weekly breakdowns.
    """
    start_of_month = target_date.replace(day=1)
    end_of_month = (start_of_month + timedelta(days=32)).replace(day=1)

    first_day_index = core_calendar.get_weekday_index(first_day_of_week)
    leading_days = (start_of_month.weekday() - first_day_index) % 7
    week_expr = func.floor((extract("day", local_start_time_expression()) + leading_days - 1) / 7) + 1

    stmt = select(
        week_expr.label("week_number"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(
            func.sum(Activity.total_timer_time),
            0.0,
        ).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label("total_elevation_gain"),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).where(
        Activity.user_id == user_id,
        *local_date_range_conditions(start_of_month, end_of_month, end_exclusive=True),
    )

    stmt, _ = _apply_activity_type_filter(stmt, activity_type)

    stmt = stmt.group_by(week_expr).order_by(week_expr)

    weekly_results = db.execute(stmt).all()
    breakdown: list[WeekSummary] = []
    overall = SummaryMetrics()

    for week_data in weekly_results:
        ws = WeekSummary(
            week_number=int(week_data.week_number),
            total_distance=float(week_data.total_distance),
            total_duration=float(week_data.total_duration),
            total_elevation_gain=float(week_data.total_elevation_gain),
            total_calories=float(week_data.total_calories),
            activity_count=int(week_data.activity_count),
        )
        breakdown.append(ws)
        overall.total_distance += ws.total_distance
        overall.total_duration += ws.total_duration
        overall.total_elevation_gain += ws.total_elevation_gain
        overall.total_calories += ws.total_calories
        overall.activity_count += ws.activity_count

    return MonthlySummaryResponse(
        total_distance=overall.total_distance,
        total_duration=overall.total_duration,
        total_elevation_gain=(overall.total_elevation_gain),
        total_calories=overall.total_calories,
        activity_count=overall.activity_count,
        breakdown=breakdown,
        type_breakdown=_get_type_breakdown(
            db,
            user_id,
            start_of_month,
            end_of_month,
            activity_type,
        ),
    )


def get_yearly_summary(
    db: Session,
    user_id: int,
    year: int,
    activity_type: str | None = None,
) -> YearlySummaryResponse:
    """
    Get yearly activity summary for a user.

    Args:
        db: Database session.
        user_id: Target user ID.
        year: Target calendar year.
        activity_type: Optional activity type
            filter name.

    Returns:
        Yearly summary with monthly breakdowns.
    """
    start_of_year = date(year, 1, 1)
    end_of_year = date(year + 1, 1, 1)

    month_expr = extract("month", local_start_time_expression())

    stmt = select(
        month_expr.label("month_number"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(
            func.sum(Activity.total_timer_time),
            0.0,
        ).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label("total_elevation_gain"),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).where(
        Activity.user_id == user_id,
        *local_date_range_conditions(start_of_year, end_of_year, end_exclusive=True),
    )

    stmt, _ = _apply_activity_type_filter(stmt, activity_type)

    stmt = stmt.group_by(month_expr).order_by(month_expr)

    monthly_results = db.execute(stmt).all()
    breakdown: list[MonthSummary] = []
    overall = SummaryMetrics()

    month_map = {m.month_number: m for m in monthly_results}

    for i in range(1, 13):
        month_data = month_map.get(i)
        if month_data:
            ms = MonthSummary(
                month_number=i,
                total_distance=float(month_data.total_distance),
                total_duration=float(month_data.total_duration),
                total_elevation_gain=float(month_data.total_elevation_gain),
                total_calories=float(month_data.total_calories),
                activity_count=int(month_data.activity_count),
            )
            breakdown.append(ms)
            overall.total_distance += ms.total_distance
            overall.total_duration += ms.total_duration
            overall.total_elevation_gain += ms.total_elevation_gain
            overall.total_calories += ms.total_calories
            overall.activity_count += ms.activity_count
        else:
            breakdown.append(MonthSummary(month_number=i))

    return YearlySummaryResponse(
        total_distance=overall.total_distance,
        total_duration=overall.total_duration,
        total_elevation_gain=(overall.total_elevation_gain),
        total_calories=overall.total_calories,
        activity_count=overall.activity_count,
        breakdown=breakdown,
        type_breakdown=_get_type_breakdown(
            db,
            user_id,
            start_of_year,
            end_of_year,
            activity_type,
        ),
    )


def get_lifetime_summary(
    db: Session,
    user_id: int,
    activity_type: str | None = None,
) -> LifetimeSummaryResponse:
    """
    Get lifetime activity summary for a user.

    Args:
        db: Database session.
        user_id: Target user ID.
        activity_type: Optional activity type
            filter name.

    Returns:
        Lifetime summary with yearly breakdowns.
    """
    # Overall metrics
    metrics_stmt = select(
        func.coalesce(func.sum(Activity.distance), 0.0).label("total_distance"),
        func.coalesce(
            func.sum(Activity.total_timer_time),
            0.0,
        ).label("total_duration"),
        func.coalesce(
            func.sum(Activity.elevation_gain),
            0.0,
        ).label("total_elevation_gain"),
        func.coalesce(func.sum(Activity.calories), 0.0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).where(Activity.user_id == user_id)

    metrics_stmt, _ = _apply_activity_type_filter(metrics_stmt, activity_type)

    totals = db.execute(metrics_stmt).one_or_none()

    # Yearly breakdown
    year_expr = extract("year", local_start_time_expression())
    yearly_stmt = select(
        year_expr.label("year_number"),
        func.coalesce(func.sum(Activity.distance), 0.0).label("total_distance"),
        func.coalesce(
            func.sum(Activity.total_timer_time),
            0.0,
        ).label("total_duration"),
        func.coalesce(
            func.sum(Activity.elevation_gain),
            0.0,
        ).label("total_elevation_gain"),
        func.coalesce(func.sum(Activity.calories), 0.0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).where(Activity.user_id == user_id)

    yearly_stmt, _ = _apply_activity_type_filter(yearly_stmt, activity_type)

    yearly_stmt = yearly_stmt.group_by(year_expr).order_by(year_expr.desc())

    yearly_rows = db.execute(yearly_stmt).all()
    breakdown: list[YearlyPeriodSummary] = []
    for row in yearly_rows:
        breakdown.append(
            YearlyPeriodSummary(
                year_number=int(row.year_number),
                total_distance=float(row.total_distance),
                total_duration=float(row.total_duration),
                total_elevation_gain=float(row.total_elevation_gain),
                total_calories=float(row.total_calories),
                activity_count=int(row.activity_count),
            )
        )

    if totals:
        return LifetimeSummaryResponse(
            total_distance=float(totals.total_distance),
            total_duration=float(totals.total_duration),
            total_elevation_gain=float(totals.total_elevation_gain),
            total_calories=float(totals.total_calories),
            activity_count=int(totals.activity_count),
            breakdown=breakdown,
            type_breakdown=(
                _get_type_breakdown(
                    db,
                    user_id,
                    date.min,
                    date.max,
                    activity_type,
                )
                or []
            ),
        )

    return LifetimeSummaryResponse(
        total_distance=0.0,
        total_duration=0.0,
        total_elevation_gain=0.0,
        total_calories=0.0,
        activity_count=0,
        breakdown=[],
        type_breakdown=[],
    )
