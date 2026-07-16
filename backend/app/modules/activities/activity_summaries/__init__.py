"""
Activity summaries sub-module for aggregated metrics.

This module provides summary aggregations of activity data
across different time periods (weekly, monthly, yearly,
lifetime) with breakdowns by day, week, month, year, and
activity type.

Exports:
    - CRUD: get_weekly_summary, get_monthly_summary,
      get_yearly_summary, get_lifetime_summary
    - Schemas: SummaryMetrics, DaySummary, WeekSummary,
      MonthSummary, YearlyPeriodSummary,
      TypeBreakdownItem, WeeklySummaryResponse,
      MonthlySummaryResponse, YearlySummaryResponse,
      LifetimeSummaryResponse
    - Dependencies: validate_view_type
"""

from .crud import (
    get_lifetime_summary,
    get_monthly_summary,
    get_weekly_summary,
    get_yearly_summary,
)
from .dependencies import validate_view_type
from .schema import (
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

__all__ = [
    "DaySummary",
    "LifetimeSummaryResponse",
    "MonthSummary",
    "MonthlySummaryResponse",
    # Pydantic schemas
    "SummaryMetrics",
    "TypeBreakdownItem",
    "WeekSummary",
    "WeeklySummaryResponse",
    "YearlyPeriodSummary",
    "YearlySummaryResponse",
    "get_lifetime_summary",
    "get_monthly_summary",
    # CRUD operations
    "get_weekly_summary",
    "get_yearly_summary",
    # Dependencies
    "validate_view_type",
]
