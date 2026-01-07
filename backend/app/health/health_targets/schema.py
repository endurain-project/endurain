from pydantic import BaseModel, ConfigDict, field_validator


class HealthTargetsBase(BaseModel):
    """
    Base schema for health targets with shared fields.

    Attributes:
        weight: Target weight in kg.
        steps: Target daily steps count.
        sleep: Target sleep duration in seconds.
    """

    weight: float | None = None
    steps: int | None = None
    sleep: int | None = None

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: float | None) -> float | None:
        """
        Validate weight is positive and reasonable.

        Args:
            v: Weight value to validate.

        Returns:
            Validated weight value.

        Raises:
            ValueError: If weight is not between 0 and 500 kg.
        """
        if v is not None and (v <= 0 or v > 500):
            raise ValueError("Weight must be between 0 and 500 kg")
        return v

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, v: int | None) -> int | None:
        """
        Validate steps is non-negative.

        Args:
            v: Steps value to validate.

        Returns:
            Validated steps value.

        Raises:
            ValueError: If steps is negative.
        """
        if v is not None and v < 0:
            raise ValueError("Steps cannot be negative")
        return v

    @field_validator("sleep")
    @classmethod
    def validate_sleep(cls, v: int | None) -> int | None:
        """
        Validate sleep duration is within reasonable bounds.

        Args:
            v: Sleep duration in seconds to validate.

        Returns:
            Validated sleep duration.

        Raises:
            ValueError: If sleep is not between 0 and 86400
                seconds (24 hours).
        """
        if v is not None and (v < 0 or v > 86400):
            raise ValueError("Sleep must be between 0 and 86400 seconds (24 hours)")
        return v


class HealthTargetsUpdate(HealthTargetsBase):
    """
    Schema for updating health targets.

    Inherits all validation from HealthTargetsBase.
    All fields are optional for partial updates.
    """


class HealthTargetsRead(HealthTargetsBase):
    """
    Schema for reading health targets.

    Attributes:
        id: Unique identifier for the health target record.
        user_id: Foreign key reference to the user.
    """

    id: int
    user_id: int

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
