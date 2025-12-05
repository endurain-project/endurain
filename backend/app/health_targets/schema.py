from pydantic import BaseModel, ConfigDict


class HealthTargets(BaseModel):
    """
    Pydantic model representing health targets for a user.

    This model defines the structure for storing and validating health-related goals
    such as weight, daily steps, and sleep duration.

    Attributes:
        id (int | None): Unique identifier for the health target record. Defaults to None.
        user_id (int | None): Foreign key reference to the user. Defaults to None.
        weight (float | None): Target weight in kilograms or pounds. Defaults to None.
        steps (int | None): Target number of daily steps. Defaults to None.
        sleep (int | None): Target sleep duration in minutes. Defaults to None.

    Configuration:
        from_attributes: Allows model creation from ORM objects.
        extra: Forbids extra fields not defined in the model.
        validate_assignment: Validates values when attributes are assigned after creation.
    """

    id: int | None = None
    user_id: int | None = None
    weight: float | None = None
    steps: int | None = None
    sleep: int | None = None

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )
