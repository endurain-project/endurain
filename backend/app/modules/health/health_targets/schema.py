"""Pydantic request and response shapes for health targets."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt


class HealthTargetsBase(BaseModel):
    """Base schema for health targets with shared fields.

    Attributes:
        weight_kg: Target weight in kg.
        steps: Target daily steps count.
        sleep_seconds: Target sleep duration in seconds.
        fasting_seconds: Target fasting duration in seconds.
        water_ml: Target daily water intake in milliliters.
        poop_count: Target daily bowel movement count.
    """

    weight_kg: StrictFloat | None = Field(default=None, gt=0, le=500, description="Target weight in kg")
    steps: StrictInt | None = Field(default=None, ge=0, description="Target daily steps count")
    sleep_seconds: StrictInt | None = Field(
        default=None, ge=0, le=86400, description="Target sleep duration in seconds"
    )
    fasting_seconds: StrictInt | None = Field(
        default=None,
        ge=0,
        le=259200,
        description="Target fasting duration in seconds (max 72h)",
    )
    water_ml: StrictFloat | None = Field(
        default=None,
        ge=0,
        le=20000,
        description=("Target daily water intake in milliliters"),
    )
    poop_count: StrictInt | None = Field(
        default=None,
        ge=0,
        le=20,
        description="Target daily bowel movement count",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthTargetsRead(HealthTargetsBase):
    """Schema for reading health targets.

    Attributes:
        id: Unique identifier for the health target record.
        user_id: Foreign key reference to the user.
        version: Optimistic-concurrency counter, also sent as the ETag.
    """

    id: uuid.UUID = Field(..., description="Unique identifier for the health target")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")
    updated_at: datetime = Field(..., description="When the record last changed, set by the server")


class HealthTargetsUpdate(HealthTargetsBase):
    """Schema for the fields a PATCH changes on a user's health targets.

    The targets belong to the caller, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """
