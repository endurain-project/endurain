from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class RouteBase(BaseModel):
    name: str = Field(..., title="Route Name", max_length=255)
    description: Optional[str] = Field(None, title="Route Description")
    activity_type: str = Field(..., title="Activity Type (e.g., cycling, running)", max_length=50)
    sub_type: Optional[str] = Field(None, title="Sub-type (e.g., road, gravel, trail)", max_length=50)
    distance: float = Field(0.0, title="Total distance in meters")
    elevation_gain: Optional[float] = Field(0.0, title="Total elevation gain in meters")
    route_data: Dict[str, Any] = Field(
        ...,
        title="Route Data",
        description="JSON object containing waypoints and full coordinates to render the map and export to GPX"
    )

class RouteCreate(RouteBase):
    pass

class RouteUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    activity_type: Optional[str] = Field(None, max_length=50)
    sub_type: Optional[str] = Field(None, max_length=50)
    distance: Optional[float] = None
    elevation_gain: Optional[float] = None
    route_data: Optional[Dict[str, Any]] = None

class RouteResponse(RouteBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
