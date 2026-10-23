"""ORM↔schema transformation for health poop records.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema


def to_read_schema(health_poop: health_poop_models.HealthPoop) -> health_poop_schema.HealthPoopRead:
    """Convert a health poop ORM row into its serialized schema.

    Args:
        health_poop: The ORM row to convert.

    Returns:
        The health poop schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_poop_schema.HealthPoopRead.model_validate(health_poop)


def to_read_schemas(
    health_poop: list[health_poop_models.HealthPoop],
) -> list[health_poop_schema.HealthPoopRead]:
    """Convert health poop ORM rows into their serialized schemas.

    Args:
        health_poop: The ORM rows to convert.

    Returns:
        The health poop schemas, in the order given.
    """
    return [to_read_schema(row) for row in health_poop]
