"""Client-facing shapes shared by the health packages."""

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, Field

import modules.health.constants as health_constants


class HealthChartPoint(BaseModel):
    """One aggregated point of a health chart.

    Attributes:
        date: First day of the bucket the point aggregates.
        value: The bucket's value, in the metric's unit.
    """

    model_config = ConfigDict(from_attributes=True)

    date: date_type
    value: float = Field(
        description=(
            "The bucket's value: the average for the weight (kilograms), steps (steps), water (milliliters), "
            "sleep (seconds) and resting heart rate (beats per minute) charts, and the number of movements for poop"
        )
    )


class HealthChartSeries(BaseModel):
    """A health metric aggregated over an interval, oldest bucket first.

    Attributes:
        bucket: The span each point aggregates.
        points: The buckets that hold data.
    """

    bucket: health_constants.ChartBucket
    points: list[HealthChartPoint]
