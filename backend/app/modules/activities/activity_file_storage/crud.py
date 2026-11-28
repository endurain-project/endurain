"""Persistence for retained activity files; every function stages and none commits."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.contracts as activity_file_storage_contracts
import modules.activities.activity_file_storage.files as activity_file_storage_files
import modules.activities.activity_file_storage.models as activity_file_storage_models
import modules.activities.activity_file_storage.serializers as activity_file_storage_serializers

_Model = activity_file_storage_models.ActivityFile
_State = activity_file_storage_constants.ActivityFileState


def take_live_file(
    user_id: uuid.UUID,
    sha256: str,
    extension: str,
    size_bytes: int,
    db: Session,
    *,
    storage_key: str | None = None,
) -> tuple[activity_file_storage_contracts.ActivityFileRef, str, bool]:
    """Stage a ``pending`` row for the user's bytes, or take the live row the same bytes already have.

    One statement settles two uploads of the same bytes: the loser of the race for the unique index takes the winner's
    row and touches its ``updated_at``, so the sweep does not age out a row an upload is still using.

    Args:
        user_id: The owner.
        sha256: Hex SHA-256 of the file.
        extension: The file's extension.
        size_bytes: The file's size.
        db: Database session.
        storage_key: The key of a blob that already exists, for a file stored before rows; ``None`` for a blob
            this row's upload is about to write under ``files/{id}``.

    Returns:
        The row's reference, its state before this call took it, and whether this call created it.
    """
    file_id = uuid.uuid4()
    stmt = (
        insert(_Model)
        .values(
            id=file_id,
            user_id=user_id,
            sha256=sha256,
            storage_key=storage_key or activity_file_storage_files.file_key(file_id, extension),
            extension=activity_file_storage_files.normalize_extension(extension),
            size_bytes=size_bytes,
            state=_State.PENDING,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "sha256"],
            index_where=text("state <> 'deleting'"),
            set_={"updated_at": func.now()},
        )
        .returning(_Model)
    )
    row = db.execute(stmt).scalar_one()
    db.flush()
    return activity_file_storage_serializers.to_ref(row), row.state, row.id == file_id


def get_named_keys(keys: Sequence[str], db: Session) -> set[str]:
    """Return which of the given storage keys a file row names, in any state.

    Args:
        keys: Storage keys.
        db: Database session.

    Returns:
        The subset some row names.
    """
    if not keys:
        return set()
    return set(db.scalars(select(_Model.storage_key).where(_Model.storage_key.in_(keys))).all())


def mark_attached(file_id: uuid.UUID, db: Session) -> bool:
    """Stage the move of a ``pending`` or ``attached`` row to ``attached``.

    Args:
        file_id: The file row.
        db: Database session.

    Returns:
        ``True`` when the row was in one of those states, ``False`` when it is gone or being deleted.
    """
    return _set_state(file_id, (_State.PENDING, _State.ATTACHED), _State.ATTACHED, db)


def mark_deleting(file_ids: Sequence[uuid.UUID], from_state: str, db: Session) -> int:
    """Stage the move of rows in one state to ``deleting``.

    Args:
        file_ids: The file rows.
        from_state: The state a row must be in to move.
        db: Database session.

    Returns:
        How many rows moved.
    """
    if not file_ids:
        return 0
    matched = core_database.rowcount(
        db,
        sa_update(_Model)
        .where(_Model.id.in_(file_ids), _Model.state == from_state)
        .values(state=_State.DELETING, updated_at=func.now()),
    )
    db.flush()
    return matched


def _set_state(file_id: uuid.UUID, from_states: tuple[str, ...], to_state: str, db: Session) -> bool:
    """Stage the move of one row from any of ``from_states`` to ``to_state``.

    Args:
        file_id: The file row.
        from_states: The states a row may move from.
        to_state: The state it moves to.
        db: Database session.

    Returns:
        Whether the row moved.
    """
    matched = core_database.rowcount(
        db,
        sa_update(_Model)
        .where(_Model.id == file_id, _Model.state.in_(from_states))
        .values(state=to_state, updated_at=func.now()),
    )
    db.flush()
    return matched == 1


def lock_attached(file_ids: Sequence[uuid.UUID], db: Session) -> list[uuid.UUID]:
    """Lock the ``attached`` rows among ``file_ids`` in id order until the transaction ends.

    A concurrent upload's foreign-key insert holds a share lock on the row it references, so this waits for it to
    commit and the caller's next read sees the reference.

    Args:
        file_ids: The file rows.
        db: Database session.

    Returns:
        The ids of the rows that are ``attached``.
    """
    if not file_ids:
        return []
    return list(
        db.scalars(
            select(_Model.id)
            .where(_Model.id.in_(file_ids), _Model.state == _State.ATTACHED)
            .order_by(_Model.id)
            .with_for_update()
        ).all()
    )


def get_deleting_ref(file_id: uuid.UUID, db: Session) -> activity_file_storage_contracts.ActivityFileRef | None:
    """Return a row that is being deleted.

    Args:
        file_id: The file row.
        db: Database session.

    Returns:
        The reference, or ``None`` when the row is gone or in another state.
    """
    row = db.scalars(select(_Model).where(_Model.id == file_id, _Model.state == _State.DELETING)).one_or_none()
    return None if row is None else activity_file_storage_serializers.to_ref(row)


def get_refs(
    file_ids: Sequence[uuid.UUID], db: Session
) -> dict[uuid.UUID, activity_file_storage_contracts.ActivityFileRef]:
    """Return the references of the given rows.

    Args:
        file_ids: The file rows.
        db: Database session.

    Returns:
        The reference by id; a missing row is absent.
    """
    if not file_ids:
        return {}
    rows = db.scalars(select(_Model).where(_Model.id.in_(file_ids))).all()
    return {row.id: activity_file_storage_serializers.to_ref(row) for row in rows}


def delete_deleting(file_ids: Sequence[uuid.UUID], db: Session) -> None:
    """Stage the removal of rows that are still being deleted.

    Args:
        file_ids: The file rows.
        db: Database session.
    """
    if not file_ids:
        return
    db.execute(sa_delete(_Model).where(_Model.id.in_(file_ids), _Model.state == _State.DELETING))
    db.flush()


def claim_stale_pending(before: datetime, limit: int, db: Session) -> int:
    """Stage the move of up to ``limit`` ``pending`` rows not touched since ``before`` to ``deleting``.

    Rows another transaction holds are skipped, so two sweeps do not wait on each other.

    Args:
        before: Rows last touched before this instant are stale.
        limit: The most rows to move.
        db: Database session.

    Returns:
        How many rows moved.
    """
    stale = (
        select(_Model.id)
        .where(_Model.state == _State.PENDING, _Model.updated_at < before)
        .order_by(_Model.updated_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    matched = core_database.rowcount(
        db,
        sa_update(_Model).where(_Model.id.in_(stale)).values(state=_State.DELETING, updated_at=func.now()),
    )
    db.flush()
    return matched


def list_attached_before(before: datetime, after_id: uuid.UUID | None, limit: int, db: Session) -> list[uuid.UUID]:
    """Return the ids of ``attached`` rows not touched since ``before``, in id order.

    Args:
        before: Rows last touched before this instant qualify.
        after_id: The last id of the previous page, or ``None`` for the first.
        limit: The most ids to return.
        db: Database session.

    Returns:
        Up to ``limit`` ids.
    """
    stmt = select(_Model.id).where(_Model.state == _State.ATTACHED, _Model.updated_at < before)
    if after_id is not None:
        stmt = stmt.where(_Model.id > after_id)
    return list(db.scalars(stmt.order_by(_Model.id).limit(limit)).all())


def list_deleting(
    after_id: uuid.UUID | None, limit: int, db: Session
) -> list[activity_file_storage_contracts.ActivityFileRef]:
    """Return the rows being deleted, in id order.

    Args:
        after_id: The last id of the previous page, or ``None`` for the first.
        limit: The most rows to return.
        db: Database session.

    Returns:
        Up to ``limit`` references.
    """
    stmt = select(_Model).where(_Model.state == _State.DELETING)
    if after_id is not None:
        stmt = stmt.where(_Model.id > after_id)
    return [
        activity_file_storage_serializers.to_ref(row) for row in db.scalars(stmt.order_by(_Model.id).limit(limit)).all()
    ]


def list_user_files(
    user_id: uuid.UUID, limit: int, db: Session
) -> list[activity_file_storage_contracts.ActivityFileRef]:
    """Return up to ``limit`` of a user's rows, in whatever state.

    Args:
        user_id: The owner.
        limit: The most rows to return.
        db: Database session.

    Returns:
        Up to ``limit`` references.
    """
    rows = db.scalars(select(_Model).where(_Model.user_id == user_id).order_by(_Model.id).limit(limit)).all()
    return [activity_file_storage_serializers.to_ref(row) for row in rows]


def delete_files(file_ids: Sequence[uuid.UUID], db: Session) -> None:
    """Stage the removal of rows in any state.

    Args:
        file_ids: The file rows.
        db: Database session.
    """
    if not file_ids:
        return
    db.execute(sa_delete(_Model).where(_Model.id.in_(file_ids)))
    db.flush()
