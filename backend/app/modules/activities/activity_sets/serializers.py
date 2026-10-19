"""ORM↔schema transformation for activity workout sets.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

from pydantic import BaseModel

import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.models as activity_sets_models
import modules.activities.activity_sets.schema as activity_sets_schema


def to_read_schema(
    orm_set: activity_sets_models.ActivitySets,
) -> activity_sets_schema.ActivitySetsRead:
    """Convert an ORM row to its Read schema.

    Args:
        orm_set: The ORM model instance.

    Returns:
        An ActivitySetsRead schema instance.
    """
    return activity_sets_schema.ActivitySetsRead.model_validate(orm_set)


def _extract_value(
    value: int | tuple | None,
) -> int | None:
    """Extract a scalar from a value that may be a tuple.

    Args:
        value: A scalar, tuple, or None.

    Returns:
        The extracted integer value or None.
    """
    if value is None:
        return None
    if isinstance(value, tuple):
        return value[0] if value[0] is not None else None
    return value


def to_orm(
    activity_set: activity_sets_contracts.ActivitySetsCreate | list,
    activity_id: int,
) -> activity_sets_models.ActivitySets:
    """Build an ORM row from a set schema or a raw FIT parser row.

    Args:
        activity_set: A ``ActivitySetsCreate`` schema, or the raw list the FIT
            parser emits (duration, repetitions, weight, set type, start time,
            category, category sub type).
        activity_id: The parent activity ID.

    Returns:
        An unsaved ActivitySets ORM instance.
    """
    if isinstance(activity_set, BaseModel):
        return activity_sets_models.ActivitySets(
            activity_id=activity_id,
            duration=activity_set.duration,
            repetitions=activity_set.repetitions,
            weight=activity_set.weight,
            set_type=activity_set.set_type,
            start_time=activity_set.start_time,
            category=activity_set.category,
            category_subtype=activity_set.category_subtype,
        )
    return activity_sets_models.ActivitySets(
        activity_id=activity_id,
        duration=activity_set[0],
        repetitions=activity_set[1],
        weight=activity_set[2],
        set_type=activity_set[3],
        start_time=activity_set[4],
        category=_extract_value(activity_set[5]),
        category_subtype=_extract_value(activity_set[6]),
    )
