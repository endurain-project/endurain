"""CRUD operations for gear components."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.gears.contracts as gears_contracts
import modules.gears.gear_components.models as gear_components_models
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.serializers as gear_components_serializers

# Fields that must never be overwritten via user-supplied data during updates.
_IMMUTABLE_FIELDS: set[str] = {
    "id",
    "user_id",
    "gear_id",
}


def _get_gear_component_model_or_404(
    gear_component_id: int, user_id: int, db: Session
) -> gear_components_models.GearComponents:
    """Load a user's component row for a write.

    Args:
        gear_component_id: Component ID to fetch.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The mapped GearComponents ORM instance.

    Raises:
        NotFoundError: If the user has no such component.
    """
    stmt = select(gear_components_models.GearComponents).where(
        gear_components_models.GearComponents.id == gear_component_id,
        gear_components_models.GearComponents.user_id == user_id,
    )
    db_gear_component = db.execute(stmt).scalar_one_or_none()
    if db_gear_component is None:
        raise core_exceptions.NotFoundError("Gear component not found")
    return db_gear_component


def get_gear_components_user(user_id: int, db: Session) -> list[gear_components_schema.GearComponentRead]:
    """Retrieve all gear components for a user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's components (empty list if none).
    """
    stmt = select(gear_components_models.GearComponents).where(
        gear_components_models.GearComponents.user_id == user_id,
    )
    return [gear_components_serializers.to_read_schema(row) for row in db.execute(stmt).scalars().all()]


def get_gear_components_user_by_gear_id(
    user_id: int,
    gear_id: int,
    db: Session,
    *,
    active: bool | None = None,
) -> list[gear_components_schema.GearComponentRead]:
    """Retrieve a user's components for one gear.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to filter by.
        db: Database session.
        active: Optional active-status filter.

    Returns:
        The matching components (empty list if none).
    """
    stmt = select(gear_components_models.GearComponents).where(
        gear_components_models.GearComponents.user_id == user_id,
        gear_components_models.GearComponents.gear_id == gear_id,
    )
    if active is not None:
        stmt = stmt.where(gear_components_models.GearComponents.active == active)
    return [gear_components_serializers.to_read_schema(row) for row in db.execute(stmt).scalars().all()]


def list_usage_windows(gear_id: int, db: Session) -> list[gears_contracts.UsageWindow]:
    """Return the date window each component of a gear was fitted for.

    Args:
        gear_id: Gear ID to list windows for.
        db: Database session.

    Returns:
        One window per component, keyed by component ID.
    """
    stmt = select(
        gear_components_models.GearComponents.id,
        gear_components_models.GearComponents.purchase_date,
        gear_components_models.GearComponents.retired_date,
    ).where(gear_components_models.GearComponents.gear_id == gear_id)
    return [
        gears_contracts.UsageWindow(key=row.id, start_date=row.purchase_date, end_date=row.retired_date)
        for row in db.execute(stmt).all()
    ]


def get_gear_components_total_cost(gear_id: int, user_id: int, db: Session) -> float:
    """Sum the purchase value of a gear's components.

    Args:
        gear_id: Gear to sum costs for.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The total cost, zero when no component has a value.
    """
    stmt = select(func.coalesce(func.sum(gear_components_models.GearComponents.purchase_value), 0)).where(
        gear_components_models.GearComponents.gear_id == gear_id,
        gear_components_models.GearComponents.user_id == user_id,
    )
    return float(db.execute(stmt).scalar_one() or 0)


def create_gear_component(
    gear_component: gear_components_schema.GearComponentCreate,
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """Stage a new gear component.

    Args:
        gear_component: Component payload to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The staged component with its generated ID.
    """
    new_gear_component = gear_components_serializers.to_orm(gear_component, user_id)
    db.add(new_gear_component)
    db.flush()
    db.refresh(new_gear_component)
    return gear_components_serializers.to_read_schema(new_gear_component)


def edit_gear_component(
    gear_component: gear_components_schema.GearComponentUpdate,
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """Stage a partial update to a user's component.

    Only the fields present in the payload change. A retired component
    (``retired_date`` set) is always inactive, while an un-retired one keeps the
    client-supplied ``active`` value. The server never infers reactivation from
    field presence, so behaviour is deterministic across every client; reactivating a
    retired component is an explicit client action (clear ``retired_date`` and set
    ``active`` to True in the same request).

    Args:
        gear_component: Component payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The updated component.

    Raises:
        NotFoundError: If the user has no such component.
    """
    db_gear_component = _get_gear_component_model_or_404(gear_component.id, user_id, db)
    for key, value in gear_component.model_dump(exclude_unset=True).items():
        if key not in _IMMUTABLE_FIELDS:
            setattr(db_gear_component, key, value)
    if db_gear_component.retired_date is not None:
        db_gear_component.active = False
    db.flush()
    db.refresh(db_gear_component)
    return gear_components_serializers.to_read_schema(db_gear_component)


def delete_gear_component(user_id: int, gear_component_id: int, db: Session) -> None:
    """Stage the deletion of a user's component.

    Args:
        user_id: Owner user ID.
        gear_component_id: Component ID to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such component.
    """
    db.delete(_get_gear_component_model_or_404(gear_component_id, user_id, db))
    db.flush()
