from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt


class HealthTargetsBase(BaseModel):
    """
    Base schema for health targets with shared fields.

    Attributes:
        weight: Target weight in kg.
        steps: Target daily steps count.
        sleep: Target sleep duration in seconds.
        fasting: Target fasting duration in seconds.
        water_ml: Target daily water intake in milliliters.
        poop_count: Target daily bowel movement count.
    """

    weight: StrictFloat | None = Field(default=None, gt=0, le=500, description="Target weight in kg")
    steps: StrictInt | None = Field(default=None, ge=0, description="Target daily steps count")
    sleep: StrictInt | None = Field(default=None, ge=0, le=86400, description="Target sleep duration in seconds")
    fasting: StrictInt | None = Field(
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
    """
    Schema for reading health targets.

    Attributes:
        id: Unique identifier for the health target record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(..., description="Unique identifier for the health target")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")


class HealthTargetsUpdate(HealthTargetsRead):
    """
    Schema for updating health targets.

    Inherits all validation from HealthTargetsRead.
    All fields are optional for partial updates.
    """
