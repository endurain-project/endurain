"""ORM↔schema transformation for health water records.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema


def to_read_schema(health_water: health_water_models.HealthWater) -> health_water_schema.HealthWaterRead:
    """Convert a health water ORM row into its serialized schema.

    Args:
        health_water: The ORM row to convert.

    Returns:
        The health water schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_water_schema.HealthWaterRead.model_validate(health_water)


def to_read_schemas(
    health_water: list[health_water_models.HealthWater],
) -> list[health_water_schema.HealthWaterRead]:
    """Convert health water ORM rows into their serialized schemas.

    Args:
        health_water: The ORM rows to convert.

    Returns:
        The health water schemas, in the order given.
    """
    return [to_read_schema(row) for row in health_water]
