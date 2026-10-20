"""ORM↔schema transformation for gear.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

from typing import Any

import modules.gears.gear.models as gears_models
import modules.gears.gear.schema as gears_schema

# Fields that must never be reassigned through an update payload
_IMMUTABLE_FIELDS: frozenset[str] = frozenset({"id", "user_id"})

# Gear text fields trimmed of surrounding whitespace on write
_TEXT_FIELDS: tuple[str, ...] = ("brand", "model", "nickname")


def to_read_schema(gear: gears_models.Gear) -> gears_schema.GearRead:
    """Convert an ORM row to its Read schema.

    Args:
        gear: The ORM row to convert.

    Returns:
        The gear as a schema.
    """
    return gears_schema.GearRead.model_validate(gear)


def _normalize_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a gear payload mapping for persistence.

    Args:
        data: Mapping of gear field names to values.

    Returns:
        The mapping with text fields trimmed and a None ``created_at`` removed so
        the column default applies.
    """
    for field in _TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            data[field] = value.strip()
    if data.get("created_at") is None:
        data.pop("created_at", None)
    return data


def to_orm(gear: gears_schema.GearBase, user_id: int) -> gears_models.Gear:
    """Build an unsaved ORM row from a create payload.

    Args:
        gear: The gear to create.
        user_id: The owning user, which overrides any ``user_id`` in the payload.

    Returns:
        An unsaved Gear instance.
    """
    data = _normalize_payload(gear.model_dump(exclude_unset=True))
    return gears_models.Gear(**{**data, "user_id": user_id})


def to_update_values(gear: gears_schema.GearUpdate) -> dict[str, Any]:
    """Return the columns an update payload may change.

    Args:
        gear: The update payload.

    Returns:
        The normalized, non-null fields that are not immutable.
    """
    data = _normalize_payload(gear.model_dump(exclude_unset=True))
    return {key: value for key, value in data.items() if key not in _IMMUTABLE_FIELDS and value is not None}
