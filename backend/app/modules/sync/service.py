"""Walk everything a user's records did since a cursor: changes and deletions, in one order.

Every record type is two sources: its records by ``(updated_at, id)`` and its tombstones by ``(deleted_at, id)``.
The walk merges all sources in ``(stamp, rank, id)`` order, where the rank is the source's place in
:data:`_SOURCES`, so a page continues exactly where the previous one stopped even when many rows share a stamp.

Rows stamped in the last :data:`SETTLE` are held back. Postgres stamps a row when its transaction starts, so a
transaction still open when a page is read can later commit a row stamped before that page's end; waiting past
the longest transaction this application runs keeps such a row from being skipped.

A record's id is an integer or a UUID depending on its type, so each source declares the :class:`_IdKind` of its
records; a tombstone's own id is always a UUID. Ids are only compared within one rank, as the last tie-break.
"""

import json
import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.sync as core_sync
import core.types as core_types
import modules.activities.activity.integration_service as activity_integration
import modules.gears.gear.integration_service as gear_integration
import modules.gears.gear_components.integration_service as gear_components_integration
import modules.health.health_fasting.integration_service as health_fasting_integration
import modules.health.health_poop.integration_service as health_poop_integration
import modules.health.health_sleep.integration_service as health_sleep_integration
import modules.health.health_steps.integration_service as health_steps_integration
import modules.health.health_targets.integration_service as health_targets_integration
import modules.health.health_water.integration_service as health_water_integration
import modules.health.health_weight.integration_service as health_weight_integration
import modules.sync.schema as sync_schema

logger = core_logger.get_logger(__name__)

#: How long a change is held back before a page reports it; longer than any transaction this application runs.
SETTLE = timedelta(minutes=2)

_Type = sync_schema.SyncType


class _Changed(Protocol):
    """A changed record as a module returns it: its id and when it last changed."""

    @property
    def id(self) -> int | uuid.UUID | None: ...

    @property
    def updated_at(self) -> datetime | None: ...


@dataclass(frozen=True)
class _IdKind[IdT: (int, uuid.UUID)]:
    """How the ids of one kind of row are read from a cursor and bounded in a keyset walk.

    Attributes:
        parse: Reads an id from its cursor string.
        first: The lowest id, before every row of a stamp.
        last: The highest id, after every row of a stamp.
    """

    parse: Callable[[str], IdT]
    first: IdT
    last: IdT


_INT_ID = _IdKind(int, 0, core_types.INT32_MAX)
_UUID_ID = _IdKind(uuid.UUID, core_types.NIL_UUID, core_types.MAX_UUID)

#: Reads a type's changed records after a position: ``(user_id, after, until, limit, db)``.
_ChangedReader = Callable[[int, Any, datetime, int, Session], Sequence[_Changed]]

#: Reads a type's tombstones after a position: ``(user_id, after, until, limit, db)``.
_DeletedReader = Callable[[int, core_sync.Position[uuid.UUID] | None, datetime, int, Session], Sequence[Any]]


@dataclass(frozen=True)
class _TypeSources:
    """Where one record type's changes and deletions come from.

    Attributes:
        sync_type: The record type.
        scope: The scope a caller needs to sync it.
        changed: Reads its changed records, each with ``id`` and ``updated_at``.
        deleted: Reads its tombstones as :class:`core.sync.Deletion`.
        change: The change model of the type.
        id_kind: The kind of id its records have.
    """

    sync_type: sync_schema.SyncType
    scope: str
    changed: _ChangedReader
    deleted: _DeletedReader
    change: type[BaseModel]
    id_kind: _IdKind[Any]


_TYPES: tuple[_TypeSources, ...] = (
    _TypeSources(
        _Type.ACTIVITY,
        "activities:read",
        activity_integration.list_changed_activities,
        activity_integration.list_activity_deletions,
        sync_schema.ActivityChange,
        _INT_ID,
    ),
    _TypeSources(
        _Type.HEALTH_WEIGHT,
        "health:read",
        health_weight_integration.list_changed_health_weight,
        health_weight_integration.list_health_weight_deletions,
        sync_schema.HealthWeightChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.HEALTH_STEPS,
        "health:read",
        health_steps_integration.list_changed_health_steps,
        health_steps_integration.list_health_steps_deletions,
        sync_schema.HealthStepsChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.HEALTH_SLEEP,
        "health:read",
        health_sleep_integration.list_changed_health_sleep,
        health_sleep_integration.list_health_sleep_deletions,
        sync_schema.HealthSleepChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.HEALTH_WATER,
        "health:read",
        health_water_integration.list_changed_health_water,
        health_water_integration.list_health_water_deletions,
        sync_schema.HealthWaterChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.HEALTH_POOP,
        "health:read",
        health_poop_integration.list_changed_health_poop,
        health_poop_integration.list_health_poop_deletions,
        sync_schema.HealthPoopChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.HEALTH_FASTING,
        "health:read",
        health_fasting_integration.list_changed_health_fasting,
        health_fasting_integration.list_health_fasting_deletions,
        sync_schema.HealthFastingChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.HEALTH_TARGETS,
        "health-targets:read",
        health_targets_integration.list_changed_health_targets,
        health_targets_integration.list_health_targets_deletions,
        sync_schema.HealthTargetsChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.GEAR,
        "gears:read",
        gear_integration.list_changed_gears,
        gear_integration.list_gear_deletions,
        sync_schema.GearChange,
        _UUID_ID,
    ),
    _TypeSources(
        _Type.GEAR_COMPONENT,
        "gears:read",
        gear_components_integration.list_changed_gear_components,
        gear_components_integration.list_gear_component_deletions,
        sync_schema.GearComponentChange,
        _UUID_ID,
    ),
)

#: The cursor format: the version of what a cursor encodes, so a cursor of an older shape is refused.
_CURSOR_FORMAT = 3

#: The place of a change in the walk: ``(stamp, rank, id)``.
_Order = tuple[datetime, int, int | uuid.UUID]


@dataclass(frozen=True)
class _Cursor:
    """Where a sync stopped, and when the server said so.

    Attributes:
        position: The ``(stamp, rank, id)`` of the last change reported, or None before the first.
        issued_at: When the cursor was issued; one older than the tombstone retention is refused.
    """

    position: _Order | None
    issued_at: datetime

    def encode(self) -> str:
        """Return the cursor as the opaque string a client sends back.

        Returns:
            The encrypted cursor.
        """
        stamp, rank, row_id = self.position if self.position is not None else (None, None, None)
        raw = {
            "f": _CURSOR_FORMAT,
            "s": stamp.isoformat() if stamp is not None else None,
            "r": rank,
            "i": str(row_id) if row_id is not None else None,
            "t": self.issued_at.isoformat(),
        }
        return core_cryptography.encrypt_token_fernet(json.dumps(raw))


class _RawCursor(BaseModel):
    f: int | None = None
    s: datetime | None = None
    r: int | None = None
    i: str | int | None = None
    t: datetime


def _id_kind(rank: int) -> _IdKind[Any]:
    # An even rank is a type's changed records, an odd one its tombstones.
    index, is_deletion = divmod(rank, 2)
    if not 0 <= index < len(_TYPES):
        raise core_exceptions.InvalidInputError("Invalid sync cursor")
    return _UUID_ID if is_deletion else _TYPES[index].id_kind


def _decode(cursor: str) -> _Cursor:
    try:
        raw = _RawCursor.model_validate_json(core_cryptography.decrypt_token_fernet(cursor) or "")
    except (ValidationError, core_exceptions.UndecryptableError) as err:
        raise core_exceptions.InvalidInputError("Invalid sync cursor") from err
    if raw.f != _CURSOR_FORMAT:
        logger.warning("Refused a sync cursor of an older format")
        raise core_exceptions.SyncExpiredError()
    if raw.s is None or raw.r is None or raw.i is None:
        return _Cursor(None, raw.t)
    try:
        row_id = _id_kind(raw.r).parse(str(raw.i))
    except ValueError as err:
        raise core_exceptions.InvalidInputError("Invalid sync cursor") from err
    return _Cursor((raw.s, raw.r, row_id), raw.t)


def _after(rank: int, position: _Order | None) -> core_sync.Position[Any] | None:
    # A source ranked before the cursor's has reported everything at the cursor's stamp, the cursor's own source
    # continues after its id, and a source ranked after it has reported nothing at that stamp yet.
    if position is None:
        return None
    stamp, cursor_rank, row_id = position
    kind = _id_kind(rank)
    if rank < cursor_rank:
        return stamp, kind.last
    if rank == cursor_rank:
        return stamp, row_id
    return stamp, kind.first


@dataclass(frozen=True)
class _Entry:
    order: _Order
    change: BaseModel


def _record_entries(source: _TypeSources, rank: int, records: Sequence[_Changed]) -> list[_Entry]:
    entries = []
    for record in records:
        if record.id is None or record.updated_at is None:
            raise ValueError(f"A stored {source.sync_type} record has no id or updated_at")
        change = source.change.model_validate({"id": record.id, "changed_at": record.updated_at, "record": record})
        entries.append(_Entry((record.updated_at, rank, record.id), change))
    return entries


def _deletion_entries(source: _TypeSources, rank: int, deletions: Sequence[core_sync.Deletion[Any]]) -> list[_Entry]:
    entries = []
    for deletion in deletions:
        change = source.change.model_validate({"id": deletion.record_id, "changed_at": deletion.deleted_at})
        stamp, tombstone_id = deletion.position
        entries.append(_Entry((stamp, rank, tombstone_id), change))
    return entries


def sync(
    user_id: int,
    scopes: Collection[str],
    db: Session,
    *,
    cursor: str | None,
    types: Collection[sync_schema.SyncType] | None,
    num_records: int,
    now: datetime,
) -> sync_schema.SyncPage:
    """Read a slice of what changed in the user's records since a cursor.

    Args:
        user_id: The authenticated user, whose records are walked.
        scopes: The caller's scopes; a type is synced only with the scope that reads it.
        db: Database session.
        cursor: The cursor of the previous page or sync, or None to start from the beginning.
        types: The record types to sync, or None for every type the scopes allow.
        num_records: The most changes to return.
        now: The current instant.

    Returns:
        The changes, the cursor to continue from and whether more are waiting.

    Raises:
        InvalidInputError: When the cursor is not one this server issued.
        PermissionDeniedError: When a requested type needs a scope the caller lacks.
        SyncExpiredError: When the cursor is older than the deletions the server remembers.
    """
    previous = _decode(cursor) if cursor else _Cursor(None, now)
    if previous.issued_at < now - core_sync.TOMBSTONE_RETENTION:
        logger.warning(
            "Refused a sync cursor older than the tombstone retention", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.SyncExpiredError()
    if types is not None:
        missing = sorted({source.scope for source in _TYPES if source.sync_type in types} - set(scopes))
        if missing:
            logger.warning(
                "Refused a sync of types the caller's scopes cannot read",
                extra=core_logger.context(user_id=user_id, missing=missing),
            )
            raise core_exceptions.PermissionDeniedError(f"Syncing these types needs {', '.join(missing)}")
    until = now - SETTLE
    entries: list[_Entry] = []
    for index, source in enumerate(_TYPES):
        if (types is not None and source.sync_type not in types) or source.scope not in scopes:
            continue
        changed_rank, deleted_rank = 2 * index, 2 * index + 1
        changed = source.changed(user_id, _after(changed_rank, previous.position), until, num_records + 1, db)
        entries.extend(_record_entries(source, changed_rank, changed))
        deleted = source.deleted(user_id, _after(deleted_rank, previous.position), until, num_records + 1, db)
        entries.extend(_deletion_entries(source, deleted_rank, deleted))
    entries.sort(key=lambda entry: entry.order)
    page = entries[:num_records]
    position = page[-1].order if page else previous.position
    return sync_schema.SyncPage.model_validate(
        {
            "changes": [entry.change for entry in page],
            "next_cursor": _Cursor(position, now).encode(),
            "has_more": len(entries) > num_records,
        }
    )
