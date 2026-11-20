"""Migration schema definitions."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)


class Migration(BaseModel):
    """Base schema for migration data.

    Attributes:
        name: Name of the migration.
        description: Description of the migration.
        executed: Whether the migration has been executed.
    """

    name: StrictStr = Field(
        ...,
        description="Migration name",
    )
    description: StrictStr = Field(
        ...,
        description="Migration description",
    )
    executed: StrictBool = Field(
        default=False,
        description="Whether the migration was executed",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class MigrationRead(Migration):
    """Schema for reading a migration record.

    Attributes:
        id: Unique migration identifier.
    """

    id: StrictInt = Field(
        ...,
        description="Unique migration ID",
    )
