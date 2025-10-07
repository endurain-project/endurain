import os
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from datetime import timedelta, date, datetime
from zoneinfo import ZoneInfo

from typing import List
from activities.activity.crud import (
    get_last_activity_timezone,
)
from activities.activity.models import Activity
from activities.activity.utils import (
    set_activity_name_based_on_activity_type,
    ACTIVITY_NAME_TO_ID,
)
from activities.activity_summaries.schema import (
    WeeklySummaryResponse,
    MonthlySummaryResponse,
    YearlySummaryResponse,
    DaySummary,
    WeekSummary,
    MonthSummary,
    SummaryMetrics,
    TypeBreakdownItem,
    LifetimeSummaryResponse,
    YearlyPeriodSummary,
)


def _get_type_breakdown(
    db: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    activity_type: str | None = None,
) -> List[TypeBreakdownItem]:
    """Helper function to get summary breakdown by activity type, optionally filtered by a specific type."""
    query = db.query(
        Activity.activity_type.label("activity_type"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label(
            "total_elevation_gain"
        ),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).filter(Activity.user_id == user_id)

    if not (start_date == date.min and end_date == date.max):
        query = query.filter(
            Activity.start_time >= start_date, Activity.start_time < end_date
        )

    if activity_type:
        activity_type_id = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
        if activity_type_id is not None:
            query = query.filter(Activity.activity_type == activity_type_id)
        else:
            return []

    query = query.group_by(Activity.activity_type).order_by(
        func.count(Activity.id).desc(), Activity.activity_type.asc()
    )

    type_results = query.all()
    type_breakdown_list = []
    for row in type_results:
        activity_type_name = set_activity_name_based_on_activity_type(row.activity_type)
        type_breakdown_list.append(
            TypeBreakdownItem(
                activity_type_id=int(row.activity_type),
                activity_type=activity_type_name,
                total_distance=float(row.total_distance),
                total_duration=float(row.total_duration),
                total_elevation_gain=float(row.total_elevation_gain),
                total_calories=float(row.total_calories),
                activity_count=int(row.activity_count),
            )
        )
    return type_breakdown_list

def tzconvert(dt, timezone):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    timestr = dt.astimezone(timezone).strftime("%Y-%m-%dT%H:%M:%S")
    return datetime.fromisoformat(timestr)

def get_weekly_summary(
    db: Session, user_id: int, target_date: date, activity_type: str | None = None
) -> WeeklySummaryResponse:
    # Set time zone for start_of_week and end_of_week to be based on the last activities time zone
    timezone_str = get_last_activity_timezone(user_id, db)
    
    timezone = (
        ZoneInfo(timezone_str)
        if timezone_str
        else ZoneInfo(os.environ.get("TZ", "UTC"))
    )
    target_date_dt = datetime.fromisoformat(target_date.strftime("%Y-%m-%dT%H:%M:%S"))
    target_date_ = tzconvert(target_date_dt, timezone)
    target_date_tz_applied = target_date_dt - target_date_ + target_date_dt

    start_of_week = target_date_tz_applied - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=7)

    # Database-agnostic ISO day of week calculation
    # For PostgreSQL: extract('isodow') returns 1-7 (Mon-Sun)
    # For MySQL: convert DAYOFWEEK (1=Sunday, 7=Saturday) to ISO format
    engine_name = db.bind.dialect.name
    if engine_name == 'postgresql':
        iso_day_of_week = extract("isodow", func.timezone(Activity.timezone, func.timezone('UTC', Activity.start_time)))
    else:  # MySQL/MariaDB and others
        iso_day_of_week = case(
            (func.dayofweek(func.convert_tz(Activity.start_time, 'UTC', Activity.timezone)) == 1, 7),  # Sunday -> 7
            else_=func.dayofweek(func.convert_tz(Activity.start_time, 'UTC', Activity.timezone)) - 1   # Mon-Sat -> 1-6
        )

    query = db.query(
        iso_day_of_week.label("day_of_week"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label(
            "total_elevation_gain"
        ),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).filter(
        Activity.user_id == user_id,
        Activity.start_time >= start_of_week,
        Activity.start_time < end_of_week,
    )

    activity_type_id = None
    if activity_type:
        activity_type_id = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
        if activity_type_id is not None:
            query = query.filter(Activity.activity_type == activity_type_id)
        else:
            query = query.filter(Activity.id == -1)  # Force no results

    query = query.group_by(iso_day_of_week).order_by(iso_day_of_week)

    daily_results = query.all()
    breakdown = []
    overall_metrics = SummaryMetrics()

    day_map = {day.day_of_week: day for day in daily_results}

    for i in range(1, 8):
        day_data = day_map.get(i)
        if day_data:
            day_summary = DaySummary(
                day_of_week=i - 1,
                total_distance=float(day_data.total_distance),
                total_duration=float(day_data.total_duration),
                total_elevation_gain=float(day_data.total_elevation_gain),
                total_calories=float(day_data.total_calories),
                activity_count=int(day_data.activity_count),
            )
            breakdown.append(day_summary)
            overall_metrics.total_distance += day_summary.total_distance
            overall_metrics.total_duration += day_summary.total_duration
            overall_metrics.total_elevation_gain += day_summary.total_elevation_gain
            overall_metrics.total_calories += day_summary.total_calories
            overall_metrics.activity_count += day_summary.activity_count
        else:
            breakdown.append(DaySummary(day_of_week=i - 1))

    return WeeklySummaryResponse(
        total_distance=overall_metrics.total_distance,
        total_duration=overall_metrics.total_duration,
        total_elevation_gain=overall_metrics.total_elevation_gain,
        total_calories=overall_metrics.total_calories,
        activity_count=overall_metrics.activity_count,
        breakdown=breakdown,
        type_breakdown=_get_type_breakdown(
            db, user_id, start_of_week, end_of_week, activity_type
        ),
    )


def get_monthly_summary(
    db: Session, user_id: int, target_date: date, activity_type: str | None = None
) -> MonthlySummaryResponse:
    timezone_str = get_last_activity_timezone(user_id, db)

    timezone = (
        ZoneInfo(timezone_str)
        if timezone_str
        else ZoneInfo(os.environ.get("TZ", "UTC"))
    )
    target_date_dt = datetime.fromisoformat(target_date.strftime("%Y-%m-%dT%H:%M:%S"))
    target_date_ = tzconvert(target_date_dt, timezone)
    target_date_tz_applied = target_date_dt - target_date_ + target_date_dt

    start_of_month = target_date.replace(day=1)
    next_month = (start_of_month + timedelta(days=32)).replace(day=1)
    end_of_month = next_month

    query = db.query(
        extract("week", func.timezone(Activity.timezone, func.timezone('UTC',Activity.start_time))).label("week_number"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label(
            "total_elevation_gain"
        ),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).filter(
        Activity.user_id == user_id,
        Activity.start_time >= start_of_month,
        Activity.start_time < end_of_month,
    )

    activity_type_id = None
    if activity_type:
        activity_type_id = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
        if activity_type_id is not None:
            query = query.filter(Activity.activity_type == activity_type_id)
        else:
            query = query.filter(Activity.id == -1)  # Force no results

    query = query.group_by("week_number").order_by("week_number")

    weekly_results = query.all()
    breakdown = []
    overall_metrics = SummaryMetrics()

    for week_data in weekly_results:
        week_summary = WeekSummary(
            week_number=int(week_data.week_number),
            total_distance=float(week_data.total_distance),
            total_duration=float(week_data.total_duration),
            total_elevation_gain=float(week_data.total_elevation_gain),
            total_calories=float(week_data.total_calories),
            activity_count=int(week_data.activity_count),
        )
        breakdown.append(week_summary)
        overall_metrics.total_distance += week_summary.total_distance
        overall_metrics.total_duration += week_summary.total_duration
        overall_metrics.total_elevation_gain += week_summary.total_elevation_gain
        overall_metrics.total_calories += week_summary.total_calories
        overall_metrics.activity_count += week_summary.activity_count

    return MonthlySummaryResponse(
        total_distance=overall_metrics.total_distance,
        total_duration=overall_metrics.total_duration,
        total_elevation_gain=overall_metrics.total_elevation_gain,
        total_calories=overall_metrics.total_calories,
        activity_count=overall_metrics.activity_count,
        breakdown=breakdown,
        type_breakdown=_get_type_breakdown(
            db, user_id, start_of_month, end_of_month, activity_type
        ),
    )


def get_yearly_summary(
    db: Session, user_id: int, year: int, activity_type: str | None = None
) -> YearlySummaryResponse:
    timezone_str = get_last_activity_timezone(user_id, db)
    
    timezone = (
        ZoneInfo(timezone_str)
        if timezone_str
        else ZoneInfo(os.environ.get("TZ", "UTC"))
    )
    start_of_year = datetime(year, 1, 1, 0, 0, 0, 0, timezone)
    start_of_year = tzconvert(start_of_year, ZoneInfo('UTC'))
    end_of_year = datetime(year + 1, 1, 1, 0, 0, 0, 0, timezone)
    end_of_year = tzconvert(end_of_year, ZoneInfo('UTC'))

    query = db.query(
        extract("month", func.timezone(Activity.timezone, func.timezone('UTC', Activity.start_time))).label("month_number"),
        func.coalesce(func.sum(Activity.distance), 0).label("total_distance"),
        func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0).label(
            "total_elevation_gain"
        ),
        func.coalesce(func.sum(Activity.calories), 0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).filter(
        Activity.user_id == user_id,
        Activity.start_time >= start_of_year,
        Activity.start_time < end_of_year,
    )

    activity_type_id = None
    if activity_type:
        activity_type_id = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
        if activity_type_id is not None:
            query = query.filter(Activity.activity_type == activity_type_id)
        else:
            query = query.filter(Activity.id == -1)  # Force no results

    query = query.group_by("month_number").order_by("month_number")

    monthly_results = query.all()
    breakdown = []
    overall_metrics = SummaryMetrics()

    month_map = {month.month_number: month for month in monthly_results}

    for i in range(1, 13):
        month_data = month_map.get(i)
        if month_data:
            month_summary = MonthSummary(
                month_number=i,
                total_distance=float(month_data.total_distance),
                total_duration=float(month_data.total_duration),
                total_elevation_gain=float(month_data.total_elevation_gain),
                total_calories=float(month_data.total_calories),
                activity_count=int(month_data.activity_count),
            )
            breakdown.append(month_summary)
            overall_metrics.total_distance += month_summary.total_distance
            overall_metrics.total_duration += month_summary.total_duration
            overall_metrics.total_elevation_gain += month_summary.total_elevation_gain
            overall_metrics.total_calories += month_summary.total_calories
            overall_metrics.activity_count += month_summary.activity_count
        else:
            breakdown.append(MonthSummary(month_number=i))
    return YearlySummaryResponse(
        total_distance=overall_metrics.total_distance,
        total_duration=overall_metrics.total_duration,
        total_elevation_gain=overall_metrics.total_elevation_gain,
        total_calories=overall_metrics.total_calories,
        activity_count=overall_metrics.activity_count,
        breakdown=breakdown,
        type_breakdown=_get_type_breakdown(
            db, user_id, start_of_year, end_of_year, activity_type
        ),
    )


def get_lifetime_summary(
    db: Session, user_id: int, activity_type: str | None = None
) -> LifetimeSummaryResponse:
    # Base query for overall metrics and yearly breakdown
    base_metrics_query = db.query(
        func.coalesce(func.sum(Activity.distance), 0.0).label("total_distance"),
        func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0.0).label(
            "total_elevation_gain"
        ),
        func.coalesce(func.sum(Activity.calories), 0.0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).filter(Activity.user_id == user_id)

    # Apply activity type filter if provided
    activity_type_id_filter = None
    if activity_type:
        activity_type_id_filter = ACTIVITY_NAME_TO_ID.get(activity_type.lower())
        if activity_type_id_filter is not None:
            base_metrics_query = base_metrics_query.filter(
                Activity.activity_type == activity_type_id_filter
            )
        else:
            # Invalid activity type, force no results for metrics
            base_metrics_query = base_metrics_query.filter(Activity.id == -1)

    overall_totals = base_metrics_query.one_or_none()

    # Yearly breakdown query
    yearly_breakdown_query = db.query(
        extract("year", Activity.start_time).label("year_number"),
        func.coalesce(func.sum(Activity.distance), 0.0).label("total_distance"),
        func.coalesce(func.sum(Activity.total_timer_time), 0.0).label("total_duration"),
        func.coalesce(func.sum(Activity.elevation_gain), 0.0).label(
            "total_elevation_gain"
        ),
        func.coalesce(func.sum(Activity.calories), 0.0).label("total_calories"),
        func.count(Activity.id).label("activity_count"),
    ).filter(Activity.user_id == user_id)

    if activity_type:  # Apply same activity type filter to breakdown
        if activity_type_id_filter is not None:
            yearly_breakdown_query = yearly_breakdown_query.filter(
                Activity.activity_type == activity_type_id_filter
            )
        else:
            yearly_breakdown_query = yearly_breakdown_query.filter(
                Activity.id == -1
            )  # Force no results

    yearly_breakdown_query = yearly_breakdown_query.group_by(
        extract("year", Activity.start_time)
    ).order_by(
        extract("year", Activity.start_time).desc()  # Show recent years first
    )

    yearly_results = yearly_breakdown_query.all()
    breakdown_list = []
    for row in yearly_results:
        breakdown_list.append(
            YearlyPeriodSummary(
                year_number=int(row.year_number),
                total_distance=float(row.total_distance),
                total_duration=float(row.total_duration),
                total_elevation_gain=float(row.total_elevation_gain),
                total_calories=float(row.total_calories),
                activity_count=int(row.activity_count),
            )
        )

    # Handle case where overall_totals might be None (e.g., no activities at all for the user/filter)
    if overall_totals:
        response = LifetimeSummaryResponse(
            total_distance=float(overall_totals.total_distance),
            total_duration=float(overall_totals.total_duration),
            total_elevation_gain=float(overall_totals.total_elevation_gain),
            total_calories=float(overall_totals.total_calories),
            activity_count=int(overall_totals.activity_count),
            breakdown=breakdown_list,
            type_breakdown=_get_type_breakdown(
                db, user_id, date.min, date.max, activity_type
            )
            or [],
        )
    else:  # No activities matching criteria
        response = LifetimeSummaryResponse(
            total_distance=0.0,
            total_duration=0.0,
            total_elevation_gain=0.0,
            total_calories=0.0,
            activity_count=0,
            breakdown=[],
            type_breakdown=[],
        )

    return response
