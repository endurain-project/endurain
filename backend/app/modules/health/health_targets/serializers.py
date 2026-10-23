"""ORM↔schema transformation for health targets.

``crud`` calls this at its edge so ORM rows never leave the persistence layer.
"""

import modules.health.health_targets.models as health_targets_models
import modules.health.health_targets.schema as health_targets_schema


def to_read_schema(
    health_targets: health_targets_models.HealthTargets,
) -> health_targets_schema.HealthTargetsRead:
    """Convert a health targets ORM row into its serialized schema.

    Args:
        health_targets: The ORM row to convert.

    Returns:
        The health targets schema.

    Raises:
        ValidationError: If the row does not satisfy the schema.
    """
    return health_targets_schema.HealthTargetsRead.model_validate(health_targets)
