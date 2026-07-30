"""Pydantic schemas for activity summary responses."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
)


class SummaryMetrics(BaseModel):
    """
    Base metrics shared by all summary responses.

    Attributes:
        total_distance: Total distance in meters.
        total_duration: Total duration in seconds.
        total_elevation_gain: Total elevation gain
            in meters.
        activity_count: Number of activities.
        total_calories: Total calories burned.
    """

    total_distance: StrictFloat = Field(
        default=0.0,
        description="Total distance in meters",
    )
    total_duration: StrictFloat = Field(
        default=0.0,
        description="Total duration in seconds",
    )
    total_elevation_gain: StrictFloat = Field(
        default=0.0,
        description="Total elevation gain in meters",
    )
    activity_count: StrictInt = Field(
        default=0,
        description="Number of activities",
    )
    total_calories: StrictFloat = Field(
        default=0.0,
        description="Total calories burned",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class DaySummary(SummaryMetrics):
    """
    Daily activity summary within a week.

    Attributes:
        day_of_week: Day of week (0=Mon, 6=Sun).
    """

    day_of_week: StrictInt = Field(
        ...,
        description=("Day of week (0=Monday, 6=Sunday)"),
    )


class WeekSummary(SummaryMetrics):
    """
    Weekly activity summary within a month.

    Attributes:
        week_number: ISO week number.
    """

    week_number: StrictInt = Field(
        ...,
        description="ISO week number",
    )


class MonthSummary(SummaryMetrics):
    """
    Monthly activity summary within a year.

    Attributes:
        month_number: Month (1=Jan, 12=Dec).
    """

    month_number: StrictInt = Field(
        ...,
        description="Month (1=January, 12=December)",
    )


class YearlyPeriodSummary(SummaryMetrics):
    """
    Yearly activity summary within lifetime view.

    Attributes:
        year_number: Calendar year.
    """

    year_number: StrictInt = Field(
        ...,
        description="Calendar year",
    )


class TypeBreakdownItem(SummaryMetrics):
    """
    Summary metrics broken down by activity type.

    Attributes:
        activity_type_id: Numeric activity type ID.
        activity_type: Human-readable type name.
    """

    activity_type_id: StrictInt = Field(
        ...,
        description="Numeric activity type ID",
    )
    activity_type: StrictStr = Field(
        ...,
        description=("Human-readable activity type name"),
    )


class WeeklySummaryResponse(SummaryMetrics):
    """
    Weekly summary with daily breakdowns.

    Attributes:
        breakdown: List of daily summaries.
        type_breakdown: Optional breakdown by type.
    """

    breakdown: list[DaySummary] = Field(
        ...,
        description="List of daily summaries",
    )
    type_breakdown: list[TypeBreakdownItem] | None = Field(
        default=None,
        description=("Optional breakdown by activity type"),
    )


class MonthlySummaryResponse(SummaryMetrics):
    """
    Monthly summary with weekly breakdowns.

    Attributes:
        breakdown: List of weekly summaries.
        type_breakdown: Optional breakdown by type.
    """

    breakdown: list[WeekSummary] = Field(
        ...,
        description="List of weekly summaries",
    )
    type_breakdown: list[TypeBreakdownItem] | None = Field(
        default=None,
        description=("Optional breakdown by activity type"),
    )


class YearlySummaryResponse(SummaryMetrics):
    """
    Yearly summary with monthly breakdowns.

    Attributes:
        breakdown: List of monthly summaries.
        type_breakdown: Optional breakdown by type.
    """

    breakdown: list[MonthSummary] = Field(
        ...,
        description="List of monthly summaries",
    )
    type_breakdown: list[TypeBreakdownItem] | None = Field(
        default=None,
        description=("Optional breakdown by activity type"),
    )


class LifetimeSummaryResponse(SummaryMetrics):
    """
    Lifetime summary with yearly breakdowns.

    Attributes:
        breakdown: List of yearly summaries.
        type_breakdown: Optional breakdown by type.
    """

    breakdown: list[YearlyPeriodSummary] = Field(
        ...,
        description="List of yearly summaries",
    )
    type_breakdown: list[TypeBreakdownItem] | None = Field(
        default=None,
        description=("Optional breakdown by activity type"),
    )
