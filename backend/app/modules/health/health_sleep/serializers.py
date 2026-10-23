"""ORM↔schema transformation for health sleep records.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema


def to_read_schema(health_sleep: health_sleep_models.HealthSleep) -> health_sleep_schema.HealthSleepRead:
    """Convert a health sleep ORM row into its serialized schema.

    Args:
        health_sleep: The ORM row to convert.

    Returns:
        The health sleep schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_sleep_schema.HealthSleepRead.model_validate(health_sleep)


def to_read_schemas(
    health_sleep: list[health_sleep_models.HealthSleep],
) -> list[health_sleep_schema.HealthSleepRead]:
    """Convert health sleep ORM rows into their serialized schemas.

    Args:
        health_sleep: The ORM rows to convert.

    Returns:
        The health sleep schemas, in the order given.
    """
    return [to_read_schema(row) for row in health_sleep]
