"""CRUD operations for gear components."""

from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.models as activity_models
import modules.gears.gear_components.models as gear_components_models
import modules.gears.gear_components.schema as gear_components_schema

# Fields that must never be overwritten via
# user-supplied data during updates.
_IMMUTABLE_FIELDS: set[str] = {
    "id",
    "user_id",
    "gear_id",
}

# Private internal helpers


@overload
def _transform_gear_components(
    gear_components: gear_components_models.GearComponents,
) -> gear_components_schema.GearComponentRead: ...


@overload
def _transform_gear_components(
    gear_components: list[gear_components_models.GearComponents],
) -> list[gear_components_schema.GearComponentRead]: ...


def _transform_gear_components(
    gear_components: gear_components_models.GearComponents | list[gear_components_models.GearComponents],
) -> gear_components_schema.GearComponentRead | list[gear_components_schema.GearComponentRead]:
    """
    Transform a gear component or list of gear components to a Pydantic schema.

    Args:
        gear_components: The gear component ORM instance or list of instances.

    Returns:
        The gear component(s) as a schema.
    """
    if isinstance(gear_components, list):
        return [gear_components_schema.GearComponentRead.model_validate(gc) for gc in gear_components]
    return gear_components_schema.GearComponentRead.model_validate(gear_components)


@core_decorators.handle_db_errors
def _get_gear_component_model_by_id_and_user_id_or_404(
    gear_component_id: int, user_id: int, db: Session
) -> gear_components_models.GearComponents:
    """
    Retrieve gear component model by ID and user ID.

    Args:
        gear_component_id: Gear component ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``GearComponents`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the gear_component from the database
    stmt = select(gear_components_models.GearComponents).where(
        gear_components_models.GearComponents.id == gear_component_id,
        gear_components_models.GearComponents.user_id == user_id,
    )
    db_gear_component = db.execute(stmt).scalar_one_or_none()

    if db_gear_component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear component not found",
        )

    return db_gear_component


# Public CRUD functions


@core_decorators.handle_db_errors
def get_gear_components_user(
    user_id: int,
    db: Session,
) -> list[gear_components_schema.GearComponentRead]:
    """
    Retrieve all gear components for a user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        List of GearComponentRead schema.

    Raises:
        HTTPException: On database error (500).
    """
    stmt = select(
        gear_components_models.GearComponents,
    ).where(
        gear_components_models.GearComponents.user_id == user_id,
    )
    db_gear_components = db.execute(stmt).scalars().all()
    return _transform_gear_components(list(db_gear_components))


@core_decorators.handle_db_errors
def get_gear_components_user_by_gear_id(
    user_id: int,
    gear_id: int,
    db: Session,
    active: bool | None = None,
) -> list[gear_components_schema.GearComponentRead]:
    """
    Retrieve gear components by user and gear.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to filter by.
        db: Database session.
        active: Optional active-status filter.

    Returns:
        List of GearComponentRead schema.

    Raises:
        HTTPException: On database error (500).
    """
    stmt = select(
        gear_components_models.GearComponents,
    ).where(
        gear_components_models.GearComponents.user_id == user_id,
        gear_components_models.GearComponents.gear_id == gear_id,
    )
    if active is not None:
        stmt = stmt.where(
            gear_components_models.GearComponents.active == active,
        )
    db_gear_components = db.execute(stmt).scalars().all()
    return _transform_gear_components(list(db_gear_components))


@core_decorators.handle_db_errors
def create_gear_component(
    gear_component: (gear_components_schema.GearComponentCreate),
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """
    Create a new gear component.

    Args:
        gear_component: Create schema data.
        user_id: Authenticated user ID (token).
        db: Database session.

    Returns:
        Created GearComponentRead schema.

    Raises:
        HTTPException: On database error (500).
    """
    new_gear_component = gear_components_models.GearComponents(
        user_id=user_id,
        gear_id=gear_component.gear_id,
        type=gear_component.type,
        brand=gear_component.brand,
        model=gear_component.model,
        purchase_date=(gear_component.purchase_date),
        active=True,
        expected_kms=(gear_component.expected_kms),
        purchase_value=(gear_component.purchase_value),
    )

    db.add(new_gear_component)
    db.commit()
    db.refresh(new_gear_component)

    return _transform_gear_components(new_gear_component)


@core_decorators.handle_db_errors
def edit_gear_component(
    gear_component: (gear_components_schema.GearComponentUpdate),
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """
    Edit an existing gear component by ID.

    Applies a partial update (only fields present in the payload are
    changed) and enforces the retired/active invariant: a retired
    component (``retired_date`` set) is always inactive, while an
    un-retired component keeps the client-supplied ``active`` value.

    Args:
        gear_component: Update schema data.
        db: Database session.

    Returns:
        Updated GearComponentRead schema.

    Raises:
        HTTPException: If not found (404) or
            database error (500).
    """
    db_gear_component = _get_gear_component_model_by_id_and_user_id_or_404(gear_component.id, user_id, db)

    gear_component_data = gear_component.model_dump(
        exclude_unset=True,
    )
    for key, value in gear_component_data.items():
        if key not in _IMMUTABLE_FIELDS:
            setattr(db_gear_component, key, value)

    # Enforce the retired/active invariant: a retired component is always
    # inactive. When the component is not retired, the client-supplied
    # ``active`` value (already applied above) is honoured as-is. The
    # server never infers reactivation from field presence, so behaviour
    # is deterministic across every client; reactivating a retired
    # component is an explicit client action (clear ``retired_date`` and
    # set ``active`` to True in the same request).
    if db_gear_component.retired_date is not None:
        db_gear_component.active = False

    db.commit()
    db.refresh(db_gear_component)

    return _transform_gear_components(db_gear_component)


@core_decorators.handle_db_errors
def delete_gear_component(
    user_id: int,
    gear_component_id: int,
    db: Session,
) -> None:
    """
    Delete a gear component by user and ID.

    Args:
        user_id: Owner user ID.
        gear_component_id: Component ID to delete.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If not found (404) or
            database error (500).
    """
    db_gear_component = _get_gear_component_model_by_id_and_user_id_or_404(gear_component_id, user_id, db)

    db.delete(db_gear_component)
    db.commit()


@core_decorators.handle_db_errors
def get_components_activity_stats(
    gear_id: int,
    db: Session,
) -> dict[int, dict[str, float]]:
    """
    Get per-component activity stats for a gear.

    Computes distance and time accumulated
    between each component's purchase_date
    and retired_date from the gear's activities.

    Both bounds are calendar dates, so they are compared against each activity's
    date *in its own timezone* rather than against the raw UTC instant. Comparing
    the instant put the boundary at UTC midnight: at UTC-8 an evening ride the day
    before a purchase counted towards the new component, and at UTC+13 a morning
    ride on the purchase day did not count at all. ``retired_date`` is inclusive,
    so activities on the day a component was retired still count towards it.

    Args:
        gear_id: Gear ID to query.
        db: Database session.

    Returns:
        Dict mapping component ID to
        {distance, time} in meters/seconds.

    Raises:
        HTTPException: On database error.
    """
    comp = (
        select(
            gear_components_models.GearComponents.id.label("comp_id"),
            gear_components_models.GearComponents.purchase_date,
            gear_components_models.GearComponents.retired_date,
        )
        .where(
            gear_components_models.GearComponents.gear_id == gear_id,
        )
        .subquery()
    )

    activity_local_date = func.date(activities_crud.local_start_time_expression(db))

    stmt = (
        select(
            comp.c.comp_id,
            func.coalesce(
                func.sum(activity_models.Activity.distance),
                0,
            ).label("distance"),
            func.coalesce(
                func.sum(activity_models.Activity.total_timer_time),
                0,
            ).label("time"),
        )
        .select_from(comp)
        .outerjoin(
            activity_models.Activity,
            (activity_models.Activity.gear_id == gear_id)
            & (activity_local_date >= comp.c.purchase_date)
            & ((comp.c.retired_date.is_(None)) | (activity_local_date <= comp.c.retired_date)),
        )
        .group_by(comp.c.comp_id)
    )

    rows = db.execute(stmt).all()
    return {
        row.comp_id: {
            "distance": float(row.distance),
            "time": float(row.time),
        }
        for row in rows
    }
