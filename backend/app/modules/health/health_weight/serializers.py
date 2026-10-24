"""ORM↔schema transformation for health weight records.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema


def to_read_schema(health_weight: health_weight_models.HealthWeight) -> health_weight_schema.HealthWeightRead:
    """Convert a health weight ORM row into its serialized schema.

    Args:
        health_weight: The ORM row to convert.

    Returns:
        The health weight schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_weight_schema.HealthWeightRead.model_validate(health_weight)


def to_read_schemas(
    health_weights: list[health_weight_models.HealthWeight],
) -> list[health_weight_schema.HealthWeightRead]:
    """Convert health weight ORM rows into their serialized schemas.

    Args:
        health_weights: The ORM rows to convert.

    Returns:
        The health weight schemas, in the order given.
    """
    return [to_read_schema(health_weight) for health_weight in health_weights]
