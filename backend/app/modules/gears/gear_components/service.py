"""Application logic for gear components.

Owns the transaction for every write the router makes. What other modules may consume
lives in :mod:`modules.gears.gear_components.integration_service`.
"""

from datetime import date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.sync as core_sync
import core.types as core_types
import modules.gears.contracts as gears_contracts
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.integration_service as gears_integration
import modules.gears.gear.schema as gears_schema
import modules.gears.gear_components.constants as gear_components_constants
import modules.gears.gear_components.crud as gear_components_crud
import modules.gears.gear_components.schema as gear_components_schema
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def _require_retired_after_purchase(purchase_date: date | None, retired_date: date | None) -> None:
    """Reject a retired date that is not after the purchase date.

    Args:
        purchase_date: The purchase date, if given.
        retired_date: The retired date, if given.

    Raises:
        InvalidInputError: If both are given and the retired date is not later.
    """
    if not gear_components_schema.is_retired_after_purchase(purchase_date, retired_date):
        raise core_exceptions.InvalidInputError("Retired date must be after purchase date")


def _require_type_for_gear(gear: gears_schema.GearRead, component_type: str) -> None:
    """Reject a component type that does not fit the gear's type.

    Args:
        gear: The gear the component belongs to.
        component_type: The component type to check.

    Raises:
        InvalidInputError: If the type is not valid for the gear type.
    """
    valid_types = gear_components_constants.COMPONENT_TYPES_BY_GEAR_TYPE.get(gear.gear_type)
    if valid_types is not None and component_type not in valid_types:
        raise core_exceptions.InvalidInputError(f"Invalid gear component type for {gear.gear_type.name.lower()}")


def count_components_outside_gear_type(
    gear_id: int, user_id: int, gear_type: gears_schema.GearType, db: Session
) -> int:
    """Count a gear's components whose type is not valid for a gear type.

    Args:
        gear_id: Gear to count components of.
        user_id: Owner user ID.
        gear_type: The gear type the components would have to fit.
        db: Database session.

    Returns:
        How many components do not fit; zero for a gear type that accepts any component.
    """
    valid_types = gear_components_constants.COMPONENT_TYPES_BY_GEAR_TYPE.get(gear_type)
    if valid_types is None:
        return 0
    return gear_components_crud.count_gear_components_outside_types(gear_id, user_id, valid_types, db)


def read_component_types() -> gear_components_schema.GearComponentTypesRead:
    """Return the valid component types, grouped by gear type.

    Returns:
        The component type lists.
    """
    return gear_components_schema.GearComponentTypesRead(
        bike=gear_components_constants.BIKE_COMPONENT_TYPES,
        shoes=gear_components_constants.SHOES_COMPONENT_TYPES,
        racquet=gear_components_constants.RACQUET_COMPONENT_TYPES,
        windsurf=gear_components_constants.WINDSURF_COMPONENT_TYPES,
    )


def list_gear_components(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
) -> core_pagination.Page[gear_components_schema.GearComponentRead]:
    """Return one page of a user's gear components with the total.

    Args:
        user_id: Owner user ID.
        db: Database session.
        page_number: Page number (1-indexed).
        num_records: Records per page.

    Returns:
        The components on the page. ``total`` counts every component the user has.
    """
    total = gear_components_crud.get_gear_components_number(user_id, db)
    records = gear_components_crud.get_gear_components_user(
        user_id, db, limit=num_records, offset=(page_number - 1) * num_records
    )
    return core_pagination.Page.build(records, total, page_number, num_records)


def list_components_for_gear(
    gear_id: int,
    user_id: int,
    db: Session,
    *,
    active: bool | None = None,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> core_pagination.Page[gear_components_schema.GearComponentUsageRead]:
    """Return one page of a gear's components with the distance and time each has accumulated.

    Each component accumulates the activities recorded against the gear between its
    purchase date and retired date.

    Args:
        gear_id: Gear ID to filter by.
        user_id: Owner user ID.
        db: Database session.
        active: Optional active-status filter.
        page_number: Page number (1-indexed).
        num_records: Records per page.

    Returns:
        The matching components on the page. ``total`` counts every match.
    """
    total = gear_components_crud.get_gear_components_number_by_gear_id(user_id, gear_id, db, active=active)
    components = gear_components_crud.get_gear_components_user_by_gear_id(
        user_id, gear_id, db, active=active, page_number=page_number, num_records=num_records
    )
    if not components:
        return core_pagination.Page.build([], total, page_number, num_records)

    windows = [
        gears_contracts.UsageWindow(key=c.id, start_date=c.purchase_date, end_date=c.retired_date)
        for c in components
        if c.purchase_date is not None
    ]
    totals = gears_contributor_registry.readers().usage_by_window(gear_id, user_id, windows, db)
    no_usage = gears_contracts.UsageTotals()
    items = [
        gear_components_schema.GearComponentUsageRead(
            **component.model_dump(),
            current_distance=totals.get(component.id, no_usage).distance,
            current_time=totals.get(component.id, no_usage).time,
        )
        for component in components
    ]
    return core_pagination.Page.build(items, total, page_number, num_records)


def create_gear_component(
    gear_component: gear_components_schema.GearComponentCreate,
    user_id: int,
    db: Session,
) -> gear_components_schema.GearComponentRead:
    """Create a component on one of the user's gears.

    Args:
        gear_component: Component payload to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The created component.

    Raises:
        NotFoundError: If the user has no such gear.
        InvalidInputError: If the component type does not fit the gear type, or the retired
            date is not after the purchase date.
    """
    _require_retired_after_purchase(gear_component.purchase_date, gear_component.retired_date)
    # Locked before the type is read, so a gear type change cannot commit between the check and the insert.
    gears_integration.lock_gear(gear_component.gear_id, user_id, db)
    gear = gears_integration.get_gear_user_by_id(user_id, gear_component.gear_id, db)
    if gear is None:
        raise core_exceptions.NotFoundError("Gear not found")

    _require_type_for_gear(gear, gear_component.type)

    created = gear_components_crud.create_gear_component(gear_component, user_id, db)
    db.commit()
    logger.info("Created a gear component", extra=core_logger.context(user_id=user_id, gear_component_id=created.id))
    return created


def restore_profile_gear_components(
    records: list[dict[str, Any]], user_id: int, ids: dict[str, dict[int, int]], db: Session
) -> int:
    """Stage the gear components of a profile archive; the caller commits.

    Each component moves onto the stored gear its archived gear was restored as; one whose gear is not
    in ``ids["gears"]`` is skipped. An archive exported before the rename carries ``expected_kms``, read as
    ``expected_usage``.

    Args:
        records: The archived components.
        user_id: The importing user.
        ids: The ids restored so far.
        db: Database session.

    Returns:
        How many components were staged.
    """
    gears_id_mapping = ids.get(gears_constants.PROFILE_ARCHIVE_KEY, {})
    restored = 0
    for record in records:
        archived_gear_id = record.get("gear_id")
        new_gear_id = gears_id_mapping.get(archived_gear_id) if isinstance(archived_gear_id, int) else None
        if new_gear_id is None:
            logger.warning("Skipped a gear component whose gear is not in the archive")
            continue
        record["gear_id"] = new_gear_id

        if "expected_kms" in record:
            legacy_threshold = record.pop("expected_kms")
            record.setdefault("expected_usage", legacy_threshold)

        record = users_profile_contracts.without_row_identity(record)
        for derived in ("current_distance", "current_time"):
            record.pop(derived, None)
        if "purchase_value" in record:
            record["purchase_value"] = core_types.money_from_archived_number(record["purchase_value"])

        try:
            gear_component = gear_components_schema.GearComponentCreate(**record)
        except ValidationError:
            logger.warning("Skipped an invalid gear component")
            continue
        if not gear_components_schema.is_retired_after_purchase(
            gear_component.purchase_date, gear_component.retired_date
        ):
            logger.warning("Skipped a gear component retired on or before its purchase date")
            continue
        gear_components_crud.create_gear_component(gear_component, user_id, db)
        restored += 1

    logger.debug("Imported gear components", extra=core_logger.context(count=restored))
    return restored


def get_gear_component(user_id: int, gear_component_id: int, db: Session) -> gear_components_schema.GearComponentRead:
    """Return one of the user's components.

    Args:
        user_id: Owner user ID.
        gear_component_id: Component ID to fetch.
        db: Database session.

    Returns:
        The component.

    Raises:
        NotFoundError: If the user has no such component.
    """
    component = gear_components_crud.get_gear_component_user_by_id(user_id, gear_component_id, db)
    if component is None:
        raise core_exceptions.NotFoundError("Gear component not found")
    return component


def edit_gear_component(
    gear_component_id: int,
    gear_component: gear_components_schema.GearComponentUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str,
) -> gear_components_schema.GearComponentRead:
    """Update one of the user's components.

    Args:
        gear_component_id: Component ID to update.
        gear_component: Component payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated component.

    Raises:
        InvalidInputError: If the type does not fit the gear type, or the resulting retired
            date is not after the resulting purchase date.
        NotFoundError: If the user has no such component.
        PreconditionFailedError: If the component changed since the client read it.
    """
    current = gear_components_crud.get_gear_component_user_by_id(user_id, gear_component_id, db)
    if current is None:
        raise core_exceptions.NotFoundError("Gear component not found")

    changed = gear_component.model_fields_set
    _require_retired_after_purchase(
        gear_component.purchase_date if "purchase_date" in changed else current.purchase_date,
        gear_component.retired_date if "retired_date" in changed else current.retired_date,
    )
    # The update refuses a null type, so a type is set exactly when the request sent one.
    if gear_component.type is not None and gear_component.type != current.type:
        gears_integration.lock_gear(current.gear_id, user_id, db)
        gear = gears_integration.get_gear_user_by_id(user_id, current.gear_id, db)
        if gear is None:
            raise core_exceptions.NotFoundError("Gear not found")
        _require_type_for_gear(gear, gear_component.type)

    with core_etag.refuse_stale_write(
        db,
        "gear component",
        lambda: gear_components_crud.get_gear_component_user_by_id(user_id, gear_component_id, db) is not None,
        "Gear component not found",
    ):
        updated = gear_components_crud.edit_gear_component(
            gear_component_id, gear_component, user_id, db, if_match=if_match
        )
        db.commit()
    logger.info("Edited a gear component", extra=core_logger.context(user_id=user_id, gear_component_id=updated.id))
    return updated


def delete_gear_component(user_id: int, gear_component_id: int, db: Session, *, if_match: str) -> None:
    """Delete one of the user's components.

    Args:
        user_id: Owner user ID.
        gear_component_id: Component ID to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such component.
        PreconditionFailedError: If the component changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db,
        "gear component",
        lambda: gear_components_crud.get_gear_component_user_by_id(user_id, gear_component_id, db) is not None,
        "Gear component not found",
    ):
        gear_components_crud.delete_gear_component(user_id, gear_component_id, db, if_match=if_match)
        db.commit()
    logger.info(
        "Deleted a gear component", extra=core_logger.context(user_id=user_id, gear_component_id=gear_component_id)
    )


def prune_gear_component_deletions(now: datetime, db: Session) -> int:
    """Delete the gear component deletion records older than the retention period.

    Args:
        now: The current time.
        db: Database session.

    Returns:
        How many records were removed.
    """
    removed = gear_components_crud.prune_gear_component_deletions(now - core_sync.TOMBSTONE_RETENTION, db)
    db.commit()
    logger.info("Pruned gear component deletion records", extra=core_logger.context(count=removed))
    return removed
