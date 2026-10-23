"""ORM↔schema transformation for health steps records.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema


def to_read_schema(health_steps: health_steps_models.HealthSteps) -> health_steps_schema.HealthStepsRead:
    """Convert a health steps ORM row into its serialized schema.

    Args:
        health_steps: The ORM row to convert.

    Returns:
        The health steps schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_steps_schema.HealthStepsRead.model_validate(health_steps)


def to_read_schemas(
    health_steps: list[health_steps_models.HealthSteps],
) -> list[health_steps_schema.HealthStepsRead]:
    """Convert health steps ORM rows into their serialized schemas.

    Args:
        health_steps: The ORM rows to convert.

    Returns:
        The health steps schemas, in the order given.
    """
    return [to_read_schema(row) for row in health_steps]
