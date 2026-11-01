"""Client-facing shapes shared by the health packages."""

from datetime import date as date_type

from pydantic import BaseModel, ConfigDict

import modules.health.constants as health_constants


class HealthChartPoint(BaseModel):
    """One aggregated point of a health chart.

    Attributes:
        date: First day of the bucket the point aggregates.
        value: The bucket's aggregated value, in the metric's stored unit.
    """

    model_config = ConfigDict(from_attributes=True)

    date: date_type
    value: float


class HealthChartSeries(BaseModel):
    """A health metric aggregated over an interval, oldest bucket first.

    Attributes:
        bucket: The span each point aggregates.
        points: The buckets that hold data.
    """

    bucket: health_constants.ChartBucket
    points: list[HealthChartPoint]
