"""Application logic for gear.

Owns the transaction for every write the router makes, and stages the writes that
other modules compose into their own unit of work. What other modules may consume
lives in :mod:`modules.gears.gear.integration_service`.
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import core.sync as core_sync
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema
import modules.users.users_profile.contracts as users_profile_contracts

logger = core_logger.get_logger(__name__)


def list_gears(
    user_id: uuid.UUID,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    active: bool | None = None,
    gear_type: gears_schema.GearType | None = None,
    nickname_contains: str | None = None,
) -> core_pagination.Page[gears_schema.GearRead]:
    """Return one page of a user's gears with the matching total.

    Args:
        user_id: Owner user ID.
        db: Database session.
        page_number: Page number (1-indexed).
        num_records: Records per page.
        active: Keep only active (``True``) or inactive (``False``) gears; ``None`` keeps both.
        gear_type: Keep only gears of this type.
        nickname_contains: Keep only gears whose nickname contains this text.

    Returns:
        The gears on the page. ``total`` counts every gear matching the filters.
    """
    total = gears_crud.get_gears_number(
        user_id, db, active=active, gear_type=gear_type, nickname_contains=nickname_contains
    )
    records = gears_crud.get_gear_users_with_pagination(
        user_id,
        db,
        page_number=page_number,
        num_records=num_records,
        active=active,
        gear_type=gear_type,
        nickname_contains=nickname_contains,
    )
    return core_pagination.Page.build(records, total, page_number, num_records)


def read_gear_detail(gear_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> gears_schema.GearDetailRead:
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
    return _with_totals(gear, user_id, db)


def _with_totals(gear: gears_schema.GearRead, user_id: uuid.UUID, db: Session) -> gears_schema.GearDetailRead:
    """Add the recorded usage and component cost to a gear.

    Args:
        gear: The gear to extend.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The gear with totals.
    """
    readers = gears_contributor_registry.readers()
    usage = readers.usage(gear.id, user_id, db)
    components_cost = readers.components_cost(gear.id, user_id, db)
    return gears_schema.GearDetailRead(
        **gear.model_dump(),
        total_distance=usage.distance + (gear.initial_distance or 0.0),
        total_time=usage.time,
        total_components_cost=f"{components_cost:.2f}",
    )


def list_changed_gears(
    user_id: uuid.UUID, after: core_sync.Position | None, until: datetime, limit: int, db: Session
) -> list[gears_schema.GearDetailRead]:
    """Return a page of a user's gears changed after a position, each with its totals.

    Args:
        user_id: Owner user ID.
        after: Return gears strictly after this ``(updated_at, id)``; None from the first.
        until: Return only gears changed before this instant.
        limit: The most gears to return.
        db: Database session.

    Returns:
        The gears with totals, in ``(updated_at, id)`` order.
    """
    return [_with_totals(gear, user_id, db) for gear in gears_crud.list_changed_gears(user_id, after, until, limit, db)]


def create_gear(gear: gears_schema.GearCreateRequest, user_id: uuid.UUID, db: Session) -> gears_schema.GearRead:
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


def stage_gears(gears: Iterable[gears_schema.GearCreate | None], user_id: uuid.UUID, db: Session) -> None:
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
            logger.debug(
                "Skipped a gear whose nickname repeats in the request",
                extra=core_logger.context(user_id=user_id, nickname=gear.nickname),
            )
            continue
        candidates[nickname] = gear

    existing = gears_crud.get_existing_nicknames(user_id, set(candidates), db) if candidates else set()
    for nickname in existing:
        logger.debug(
            "Skipped a gear whose nickname already exists",
            extra=core_logger.context(user_id=user_id, nickname=candidates[nickname].nickname),
        )

    new_gears = [gear for nickname, gear in candidates.items() if nickname not in existing]
    if new_gears:
        gears_crud.create_gears(new_gears, user_id, db)


def restore_profile_gears(
    records: list[dict[str, Any]], user_id: uuid.UUID, ids: users_profile_contracts.ProfileIdMaps, db: Session
) -> int:
    """Stage the gears of a profile archive; the caller commits.

    A gear whose nickname the user already has maps onto that gear. A provider gear ID the user already
    holds on another gear is dropped, so the archive cannot make the import fail. The archived ids
    (UUIDs) are mapped to the stored UUIDs, which are published under ``ids["gears"]``, even when the archive
    lists none.

    Args:
        records: The archived gears.
        user_id: The importing user.
        ids: The ids restored so far; receives this section's.
        db: Database session.

    Returns:
        How many gears were restored or matched.
    """
    mapping: dict[uuid.UUID, uuid.UUID] = {}
    ids[gears_constants.PROFILE_ARCHIVE_KEY] = mapping
    restored = 0
    for record in records:
        original_id = users_profile_contracts.archived_id(record.get("id"))
        fields: dict[str, Any] = {**users_profile_contracts.without_row_identity(record), "user_id": user_id}

        try:
            gear = gears_schema.GearCreate(**fields)
        except ValidationError:
            logger.warning("Skipped an invalid gear")
            continue
        new_id = _restore_gear(gear, user_id, db)
        # Only an archived id can be named by the archive's components and default gear.
        if original_id is not None:
            mapping[original_id] = new_id
        restored += 1

    logger.debug("Imported gears", extra=core_logger.context(count=restored))
    return restored


def _restore_gear(gear: gears_schema.GearCreate, user_id: uuid.UUID, db: Session) -> uuid.UUID:
    """Stage one archived gear, tolerating what the user already has.

    Args:
        gear: The gear from the archive.
        user_id: The importing user.
        db: Database session.

    Returns:
        The ID of the gear the archived one maps to.
    """
    existing = gears_crud.get_gear_user_by_nickname(user_id, gear.nickname, db)
    if existing is not None:
        return existing.id
    try:
        with db.begin_nested():
            return gears_crud.create_gear(gear, user_id, db).id
    except core_exceptions.ConflictError:
        existing = gears_crud.get_gear_user_by_nickname(user_id, gear.nickname, db)
        if existing is not None:
            return existing.id
        logger.warning("Dropped the provider gear IDs of an imported gear that are already taken")
    without_ids = gear.model_copy(update={"strava_gear_id": None, "garminconnect_gear_id": None})
    with db.begin_nested():
        return gears_crud.create_gear(without_ids, user_id, db).id


def _require_components_fit_type_change(
    gear_id: uuid.UUID, new_type: gears_schema.GearType, user_id: uuid.UUID, db: Session, *, if_match: str
) -> None:
    """Refuse a gear type change that leaves components the new type does not allow.

    The gear row is locked first, so a component create, which locks it too, cannot add a
    component of the old type between this check and the commit. The ``If-Match`` precondition is checked
    against the locked row before the components are counted, so a stale edit answers 412, not 409.

    Args:
        gear_id: The gear being edited.
        new_type: The gear type the edit sets.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such gear.
        PreconditionFailedError: If the gear changed since the client read it.
        ComponentsOutsideGearTypeError: If the type changes and a component is not valid for the new type.
    """
    gears_crud.lock_gear(gear_id, user_id, db)
    current = gears_crud.get_gear_user_by_id(user_id, gear_id, db)
    if current is None:
        return
    core_etag.require_if_match(if_match, current.version, "gear")
    if current.gear_type == new_type:
        return
    readers = gears_contributor_registry.readers()
    if readers.count_components_outside_type(gear_id, user_id, new_type, db) > 0:
        raise core_exceptions.ComponentsOutsideGearTypeError()


def edit_gear(
    gear_id: uuid.UUID,
    gear: gears_schema.GearUpdate,
    user_id: uuid.UUID,
    db: Session,
    *,
    if_match: str,
) -> gears_schema.GearRead:
    """Update a user's gear.

    Changing the gear type locks the gear until the commit and is refused while the gear has
    components that are not valid for the new type.

    Args:
        gear_id: Gear ID to update.
        gear: Gear payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated gear.

    Raises:
        NotFoundError: If the user has no such gear.
        ConflictError: If the new nickname is already taken.
        ComponentsOutsideGearTypeError: If the gear type changes while the gear has components that are
            not valid for the new type.
        PreconditionFailedError: If the gear changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db,
        "gear",
        lambda: gears_crud.get_gear_user_by_id(user_id, gear_id, db) is not None,
        "Gear not found",
    ):
        if gear.gear_type is not None:
            _require_components_fit_type_change(gear_id, gear.gear_type, user_id, db, if_match=if_match)
        updated = gears_crud.edit_gear(gear_id, gear, user_id, db, if_match=if_match)
        db.commit()
    logger.info("Edited a gear", extra=core_logger.context(user_id=user_id, gear_id=gear_id))
    return updated


def delete_gear(gear_id: uuid.UUID, user_id: uuid.UUID, db: Session, *, if_match: str) -> None:
    """Delete a user's gear, unassigning it from their activities first.

    Args:
        gear_id: Gear ID to delete.
        user_id: Owner user ID.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such gear.
        PreconditionFailedError: If the gear changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db,
        "gear",
        lambda: gears_crud.get_gear_user_by_id(user_id, gear_id, db) is not None,
        "Gear not found",
    ):
        # Locked first, so an activity cannot be assigned the gear between the clear and the delete.
        gears_crud.lock_gear(gear_id, user_id, db)
        gears_contributor_registry.readers().clear_activities_gear(gear_id, user_id, db)
        gears_contributor_registry.readers().clear_default_gear([gear_id], user_id, db)
        gears_contributor_registry.readers().record_component_deletions([gear_id], user_id, db)
        gears_crud.delete_gear(gear_id, user_id, db, if_match=if_match)
        db.commit()
    logger.info("Deleted a gear", extra=core_logger.context(user_id=user_id, gear_id=gear_id))


def delete_all_strava_gear_for_user(user_id: uuid.UUID, db: Session) -> None:
    """Stage the deletion of every Strava-linked gear a user has, unassigning it from their default gear first.

    The components the deletion cascades away are recorded as deleted.

    Args:
        user_id: Owner user ID.
        db: Database session.
    """
    gear_ids = gears_crud.get_strava_gear_ids_for_user(user_id, db)
    gears_contributor_registry.readers().clear_default_gear(gear_ids, user_id, db)
    gears_contributor_registry.readers().record_component_deletions(gear_ids, user_id, db)
    gears_crud.delete_all_strava_gear_for_user(user_id, db)


def require_owned_gears(user_id: uuid.UUID, gear_ids: Iterable[uuid.UUID | None], db: Session) -> None:
    """Require every given gear to belong to the user.

    Gear ids arrive from the client on several write paths, so each must be resolved
    through the owner-scoped lookup before it is stored. ``None`` (clearing a gear) is always allowed.

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


def prune_gear_deletions(now: datetime, db: Session) -> int:
    """Delete the gear deletion records older than the retention period.

    Args:
        now: The current time.
        db: Database session.

    Returns:
        How many records were removed.
    """
    removed = gears_crud.prune_gear_deletions(now - core_sync.TOMBSTONE_RETENTION, db)
    db.commit()
    logger.info("Pruned gear deletion records", extra=core_logger.context(count=removed))
    return removed
