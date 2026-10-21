"""CRUD operations for gear components."""

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.gears.gear_components.models as gear_components_models
import modules.gears.gear_components.schema as gear_components_schema
import modules.gears.gear_components.serializers as gear_components_serializers


def _find_gear_component_model(
    gear_component_id: int, user_id: int, db: Session
) -> gear_components_models.GearComponents | None:
    """Load a user's component row.

    Args:
        gear_component_id: Component ID to fetch.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The mapped GearComponents ORM instance, or None if the user has no such component.
    """
    stmt = select(gear_components_models.GearComponents).where(
        gear_components_models.GearComponents.id == gear_component_id,
        gear_components_models.GearComponents.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


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
    db_gear_component = _find_gear_component_model(gear_component_id, user_id, db)
    if db_gear_component is None:
        raise core_exceptions.NotFoundError("Gear component not found")
    return db_gear_component


def get_gear_component_user_by_id(
    user_id: int, gear_component_id: int, db: Session
) -> gear_components_schema.GearComponentRead | None:
    """Retrieve a user's component by ID.

    Args:
        user_id: Owner user ID.
        gear_component_id: Component ID to fetch.
        db: Database session.

    Returns:
        The component, or None if the user has no such component.
    """
    row = _find_gear_component_model(gear_component_id, user_id, db)
    return gear_components_serializers.to_read_schema(row) if row is not None else None


def get_gear_components_number(user_id: int, db: Session) -> int:
    """Count a user's gear components.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Number of components the user has.
    """
    stmt = select(func.count(gear_components_models.GearComponents.id)).where(
        gear_components_models.GearComponents.user_id == user_id
    )
    return db.execute(stmt).scalar_one()


def get_gear_components_user(
    user_id: int, db: Session, *, limit: int | None = None, offset: int = 0
) -> list[gear_components_schema.GearComponentRead]:
    """Retrieve a user's gear components, ordered by ID.

    Args:
        user_id: Owner user ID.
        db: Database session.
        limit: Maximum number of components to return; all of them when omitted.
        offset: Number of components to skip.

    Returns:
        The user's components (empty list if none).
    """
    stmt = (
        select(gear_components_models.GearComponents)
        .where(gear_components_models.GearComponents.user_id == user_id)
        .order_by(gear_components_models.GearComponents.id)
        .offset(offset)
        .limit(limit)
    )
    return [gear_components_serializers.to_read_schema(row) for row in db.execute(stmt).scalars().all()]


def _filter_gear_components(stmt: Select, user_id: int, gear_id: int, *, active: bool | None) -> Select:
    """Scope a component statement to one of a user's gears and the active filter.

    Args:
        stmt: The statement to filter.
        user_id: Owner user ID.
        gear_id: Gear ID to filter by.
        active: Optional active-status filter.

    Returns:
        The filtered statement.
    """
    stmt = stmt.where(
        gear_components_models.GearComponents.user_id == user_id,
        gear_components_models.GearComponents.gear_id == gear_id,
    )
    if active is not None:
        stmt = stmt.where(gear_components_models.GearComponents.active == active)
    return stmt


def get_gear_components_number_by_gear_id(
    user_id: int, gear_id: int, db: Session, *, active: bool | None = None
) -> int:
    """Count a user's components for one gear.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to filter by.
        db: Database session.
        active: Optional active-status filter.

    Returns:
        Number of matching components.
    """
    stmt = _filter_gear_components(
        select(func.count(gear_components_models.GearComponents.id)), user_id, gear_id, active=active
    )
    return db.execute(stmt).scalar_one()


def get_gear_components_user_by_gear_id(
    user_id: int,
    gear_id: int,
    db: Session,
    *,
    active: bool | None = None,
    page_number: int = 1,
    num_records: int = core_pagination.MAX_NUM_RECORDS,
) -> list[gear_components_schema.GearComponentRead]:
    """Retrieve one page of a user's components for one gear, ordered by ID.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to filter by.
        db: Database session.
        active: Optional active-status filter.
        page_number: Page number (1-indexed).
        num_records: Records per page.

    Returns:
        The matching components on the page (empty list if none).
    """
    stmt = _filter_gear_components(select(gear_components_models.GearComponents), user_id, gear_id, active=active)
    stmt = stmt.order_by(gear_components_models.GearComponents.id)
    stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)
    return [gear_components_serializers.to_read_schema(row) for row in db.execute(stmt).scalars().all()]


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

    Raises:
        NotFoundError: If the gear was deleted before the component could be stored.
    """
    new_gear_component = gear_components_serializers.to_orm(gear_component, user_id)
    try:
        db.add(new_gear_component)
        db.flush()
    except IntegrityError as err:
        # The only constraint a payload can break is the gear it names, deleted since the caller checked.
        raise core_exceptions.NotFoundError("Gear not found") from err
    db.refresh(new_gear_component)
    return gear_components_serializers.to_read_schema(new_gear_component)


def edit_gear_component(
    gear_component_id: int,
    gear_component: gear_components_schema.GearComponentUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str | None = None,
) -> gear_components_schema.GearComponentRead:
    """Stage a partial update to a user's component.

    Only the fields present in the payload change. A retired component
    (``retired_date`` set) is always inactive, while an un-retired one keeps the
    client-supplied ``active`` value. The server never infers reactivation from
    field presence, so behaviour is deterministic across every client; reactivating a
    retired component is an explicit client action (clear ``retired_date`` and set
    ``active`` to True in the same request).

    Args:
        gear_component_id: Component ID to update.
        gear_component: Component payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition, or None. Checked against the row this
            function edits, so the flush's ``version_id_col`` guard holds the write to
            the same version.

    Returns:
        The updated component.

    Raises:
        NotFoundError: If the user has no such component.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_gear_component = _get_gear_component_model_or_404(gear_component_id, user_id, db)
    core_etag.require_if_match(if_match, db_gear_component.version, "gear component")
    for key, value in gear_component.model_dump(exclude_unset=True).items():
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
