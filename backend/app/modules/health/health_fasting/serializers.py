"""ORM↔schema transformation for health fasting records.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema


def to_read_schema(health_fasting: health_fasting_models.HealthFasting) -> health_fasting_schema.HealthFastingRead:
    """Convert a health fasting ORM row into its serialized schema.

    Args:
        health_fasting: The ORM row to convert.

    Returns:
        The health fasting schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_fasting_schema.HealthFastingRead.model_validate(health_fasting)


def to_read_schemas(
    health_fasting: list[health_fasting_models.HealthFasting],
) -> list[health_fasting_schema.HealthFastingRead]:
    """Convert health fasting ORM rows into their serialized schemas.

    Args:
        health_fasting: The ORM rows to convert.

    Returns:
        The health fasting schemas, in the order given.
    """
    return [to_read_schema(row) for row in health_fasting]
