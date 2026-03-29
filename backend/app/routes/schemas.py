from pydantic import BaseModel, Field, ConfigDict
from typing import Any
from datetime import datetime

class RouteBase(BaseModel):
    name: str = Field(..., title="Route Name", max_length=255)
    description: str | None = Field(None, title="Route Description")
    activity_type: str = Field(..., title="Activity Type (e.g., cycling, running)", max_length=50)
    sub_type: str | None = Field(None, title="Sub-type (e.g., road, gravel, trail)", max_length=50)
    distance: float = Field(0.0, title="Total distance in meters")
    elevation_gain: float | None = Field(0.0, title="Total elevation gain in meters")
    route_data: dict[str, Any] = Field(
        ...,
        title="Route Data",
        description="JSON object containing waypoints and full coordinates to render the map and export to GPX"
    )

class RouteCreate(RouteBase):
    pass

class RouteUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    activity_type: str | None = Field(None, max_length=50)
    sub_type: str | None = Field(None, max_length=50)
    distance: float | None = None
    elevation_gain: float | None = None
    route_data: dict[str, Any] | None = None

class RouteResponse(RouteBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class RouteSearchSuggestionResponse(BaseModel):
    id: str
    label: str
    meta: str
    lat: float
    lon: float
