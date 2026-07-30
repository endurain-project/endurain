"""
Activity summaries sub-module for aggregated metrics.

This module provides summary aggregations of activity data
across different time periods (weekly, monthly, yearly,
lifetime) with breakdowns by day, week, month, year, and
activity type.

Exports:
    - Service: build_summary
    - CRUD: get_weekly_summary, get_monthly_summary,
      get_yearly_summary, get_lifetime_summary
    - Schemas: SummaryMetrics, DaySummary, WeekSummary,
      MonthSummary, YearlyPeriodSummary,
      TypeBreakdownItem, WeeklySummaryResponse,
      MonthlySummaryResponse, YearlySummaryResponse,
      LifetimeSummaryResponse
"""

from .crud import (
    get_lifetime_summary,
    get_monthly_summary,
    get_weekly_summary,
    get_yearly_summary,
)
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
from .service import build_summary

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
    # Service
    "build_summary",
    "get_lifetime_summary",
    "get_monthly_summary",
    # CRUD operations
    "get_weekly_summary",
    "get_yearly_summary",
]
