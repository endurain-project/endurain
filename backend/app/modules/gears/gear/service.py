"""Application logic for gear.

Owns the transaction for every write the router makes, and stages the writes that
other modules compose into their own unit of work. What other modules may consume
lives in :mod:`modules.gears.gear.integration_service`.
"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema

logger = core_logger.get_logger(__name__)


def list_gears(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    show_inactive: bool | None = None,
    gear_type: gears_schema.GearType | None = None,
    nickname_contains: str | None = None,
) -> core_pagination.Page[gears_schema.GearRead]:
    """Return one page of a user's gears with the matching total.

    Args:
        user_id: Owner user ID.
        db: Database session.
        page_number: Page number (1-indexed).
        num_records: Records per page.
        show_inactive: Include inactive gears; ``None`` keeps the default of including them.
        gear_type: Keep only gears of this type.
        nickname_contains: Keep only gears whose nickname contains this text.

    Returns:
        The gears on the page. ``total`` counts every gear matching the filters.
    """
    filters = {"show_inactive": show_inactive, "gear_type": gear_type, "nickname_contains": nickname_contains}
    total = gears_crud.get_gears_number(user_id, db, **filters)
    records = gears_crud.get_gear_users_with_pagination(
        user_id, db, page_number=page_number, num_records=num_records, **filters
    )
    return core_pagination.Page.build(records, total, page_number, num_records)


def read_gear_detail(gear_id: int, user_id: int, db: Session) -> gears_schema.GearDetailRead:
    """Return a user's gear with its recorded usage and component cost.

    Args:
        gear_id: Gear ID to read.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The gear with totals.

    Raises:
        NotFoundError: If the user has no such gear.
    """
    gear = gears_crud.get_gear_user_by_id(user_id, gear_id, db)
    if gear is None:
        raise core_exceptions.NotFoundError("Gear not found")
    readers = gears_contributor_registry.readers()
    usage = readers.usage(gear_id, user_id, db)
    components_cost = readers.components_cost(gear_id, user_id, db)
    initial_kms_m = float(gear.initial_kms or 0) * 1000
    return gears_schema.GearDetailRead(
        **gear.model_dump(),
        total_distance=usage.distance + initial_kms_m,
        total_time=usage.time,
        total_components_cost=components_cost,
    )


def create_gear(gear: gears_schema.GearCreateRequest, user_id: int, db: Session) -> gears_schema.GearRead:
    """Create a gear for a user.

    Args:
        gear: Gear payload to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The created gear.

    Raises:
        ConflictError: If the user already has a gear with that nickname.
    """
    created = gears_crud.create_gear(gear, user_id, db)
    db.commit()
    logger.info("Created a gear", extra=core_logger.context(user_id=user_id, gear_id=created.id))
    return created


def stage_gears(gears: Iterable[gears_schema.GearCreate | None], user_id: int, db: Session) -> None:
    """Stage new gears for a user; the caller commits.

    Drops entries without a nickname, repeated nicknames and nicknames the user already
    has, so a re-sync from a provider adds only what is new.

    Args:
        gears: Gear payloads to create.
        user_id: Owner user ID.
        db: Database session.

    Raises:
        ConflictError: If a Strava or Garmin Connect gear ID is already taken.
    """
    candidates: dict[str, gears_schema.GearCreate] = {}
    for gear in gears:
        if gear is None or not str(gear.nickname).strip():
            continue
        nickname = gears_schema.normalize_nickname(gear.nickname)
        if nickname in candidates:
            logger.warning(
                "Skipped a gear whose nickname repeats in the request",
                extra=core_logger.context(user_id=user_id, nickname=gear.nickname),
            )
            continue
        candidates[nickname] = gear

    existing = gears_crud.get_existing_nicknames(user_id, set(candidates), db) if candidates else set()
    for nickname in existing:
        logger.warning(
            "Skipped a gear whose nickname already exists",
            extra=core_logger.context(user_id=user_id, nickname=candidates[nickname].nickname),
        )

    new_gears = [gear for nickname, gear in candidates.items() if nickname not in existing]
    if new_gears:
        gears_crud.create_gears(new_gears, user_id, db)


def edit_gear(
    gear_id: int,
    gear: gears_schema.GearUpdate,
    user_id: int,
    db: Session,
    *,
    if_match: str | None = None,
) -> gears_schema.GearRead:
    """Update a user's gear.

    Args:
        gear_id: Gear ID to update.
        gear: Gear payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition, or None.

    Returns:
        The updated gear.

    Raises:
        NotFoundError: If the user has no such gear.
        ConflictError: If the new nickname is already taken.
        PreconditionFailedError: If the gear changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db,
        "gear",
        lambda: gears_crud.get_gear_user_by_id(user_id, gear_id, db) is not None,
        "Gear not found",
    ):
        updated = gears_crud.edit_gear(gear_id, gear, user_id, db, if_match=if_match)
        db.commit()
    logger.info("Edited a gear", extra=core_logger.context(user_id=user_id, gear_id=gear_id))
    return updated


def delete_gear(gear_id: int, user_id: int, db: Session) -> None:
    """Delete a user's gear, unassigning it from their activities first.

    Args:
        gear_id: Gear ID to delete.
        user_id: Owner user ID.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such gear.
    """
    if gears_crud.get_gear_user_by_id(user_id, gear_id, db) is None:
        raise core_exceptions.NotFoundError("Gear not found")
    gears_contributor_registry.readers().clear_activities_gear(gear_id, user_id, db)
    gears_crud.delete_gear(gear_id, user_id, db)
    db.commit()
    logger.info("Deleted a gear", extra=core_logger.context(user_id=user_id, gear_id=gear_id))


def require_owned_gears(user_id: int, gear_ids: Iterable[int | None], db: Session) -> None:
    """Require every given gear to belong to the user.

    Gear ids arrive from the client on several write paths, and they are small
    sequential integers, so each must be resolved through the owner-scoped lookup
    before it is stored. ``None`` (clearing a gear) is always allowed.

    Args:
        user_id: The user who must own the gears.
        gear_ids: Client-supplied gear IDs; ``None`` entries are skipped.
        db: Database session.

    Raises:
        NotFoundError: If a gear does not exist or is not the user's.
    """
    for gear_id in {gear_id for gear_id in gear_ids if gear_id is not None}:
        if gears_crud.get_gear_user_by_id(user_id, gear_id, db) is None:
            raise core_exceptions.NotFoundError("Gear not found")
