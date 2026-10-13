"""Pydantic schemas for weekly streak responses."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
)


class StreakWeek(BaseModel):
    """
    Activity count for one week of the streak history.

    Attributes:
        week_start: First day of the week.
        activity_count: Counted activities in the week.
        met: Whether the weekly target was reached.
    """

    week_start: date = Field(..., description="First day of the week")
    activity_count: StrictInt = Field(..., ge=0, description="Counted activities in the week")
    met: StrictBool = Field(..., description="Whether the weekly target was reached")

    model_config = ConfigDict(extra="forbid")


class WeeklyStreakResponse(BaseModel):
    """
    Weekly streak status for a user.

    Attributes:
        current_streak: Consecutive weeks meeting the target,
            ending with the current week if it is already met,
            otherwise with the previous week.
        current_streak_start: First week of the current streak.
        longest_streak: Longest run of consecutive weeks ever.
        longest_streak_start: First week of the longest run.
        longest_streak_end: Last week of the longest run.
        current_week_start: First day of the current week.
        current_week_count: Counted activities this week.
        current_week_met: Whether this week's target is met.
        at_risk: True when a streak is running but the current
            week's target is not met yet.
        min_activities_per_week: Weekly target in effect.
        activity_types: Activity type IDs counted (None = all).
        recent_weeks: Most recent weeks, oldest first, ending
            with the current week.
    """

    current_streak: StrictInt = Field(..., ge=0)
    current_streak_start: date | None = Field(default=None)
    longest_streak: StrictInt = Field(..., ge=0)
    longest_streak_start: date | None = Field(default=None)
    longest_streak_end: date | None = Field(default=None)
    current_week_start: date
    current_week_count: StrictInt = Field(..., ge=0)
    current_week_met: StrictBool
    at_risk: StrictBool
    min_activities_per_week: StrictInt = Field(..., ge=1)
    activity_types: list[StrictInt] | None = Field(default=None)
    recent_weeks: list[StreakWeek]

    model_config = ConfigDict(extra="forbid")
