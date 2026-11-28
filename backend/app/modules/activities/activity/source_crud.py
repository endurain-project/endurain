"""Persistence for the sources of an activity: the provider ids and file hashes that identify it.

Two unique indexes make a source identity unique per user: one on a provider id (per kind and recording start) and one
on a file hash (per recording start). They are what settles two imports of the same activity racing each other.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, text
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.models as activity_models


def to_orm(user_id: uuid.UUID, source: activity_contracts.NewSource) -> activity_models.ActivitySource:
    """Build the row a new source persists.

    Args:
        user_id: The owner of the activity.
        source: The source to store.

    Returns:
        The row, not yet attached to an activity.
    """
    return activity_models.ActivitySource(
        user_id=user_id,
        kind=source.kind,
        provider_id=source.provider_id,
        file_sha256=source.file_sha256,
        session_start=source.session_start,
        precedence=source.precedence,
    )


def _identity(user_id: uuid.UUID, source: activity_contracts.NewSource) -> list[ColumnElement[bool]]:
    """Build the conditions that select the row holding a source's identity, as the unique indexes see it.

    Args:
        user_id: The owner.
        source: The identity to look up.

    Returns:
        The where-clause conditions.
    """
    columns = activity_models.ActivitySource
    conditions = [
        columns.user_id == user_id,
        columns.session_start.is_not_distinct_from(source.session_start),
    ]
    if source.provider_id is not None:
        conditions += [columns.kind == source.kind, columns.provider_id == source.provider_id]
    else:
        conditions.append(columns.file_sha256 == source.file_sha256)
    return conditions


def get_activity_id_by_source(
    user_id: uuid.UUID, source: activity_contracts.NewSource, db: Session
) -> uuid.UUID | None:
    """Return the activity a user's source identity already belongs to.

    Args:
        user_id: The owner.
        source: The identity: a provider id or a file hash, with its recording start.
        db: Database session.

    Returns:
        The activity's id, or ``None`` when the user has no such source.
    """
    return db.scalars(
        select(activity_models.ActivitySource.activity_id).where(*_identity(user_id, source)).limit(1)
    ).first()


def provider_source_exists(user_id: uuid.UUID, kind: str, provider_id: int, db: Session) -> bool:
    """Return whether a user has a source of a provider activity, whichever recording of it.

    Args:
        user_id: The owner.
        kind: ``garmin`` or ``strava``.
        provider_id: The provider's activity id.
        db: Database session.

    Returns:
        ``True`` when a source with that id exists.
    """
    return (
        db.scalars(
            select(activity_models.ActivitySource.id)
            .where(
                activity_models.ActivitySource.user_id == user_id,
                activity_models.ActivitySource.kind == kind,
                activity_models.ActivitySource.provider_id == provider_id,
            )
            .limit(1)
        ).first()
        is not None
    )


def has_sources(activity_id: uuid.UUID, db: Session) -> bool:
    """Return whether an activity has any source.

    Args:
        activity_id: The activity.
        db: Database session.

    Returns:
        ``True`` when at least one source row belongs to it.
    """
    return (
        db.scalars(
            select(activity_models.ActivitySource.id)
            .where(activity_models.ActivitySource.activity_id == activity_id)
            .limit(1)
        ).first()
        is not None
    )


def add_source_if_absent(
    activity_id: uuid.UUID, user_id: uuid.UUID, source: activity_contracts.NewSource, db: Session
) -> bool:
    """Stage a source unless the user already holds its identity.

    Args:
        activity_id: The activity the source belongs to.
        user_id: The owner.
        source: The source to store.
        db: Database session; the caller commits.

    Returns:
        ``True`` when the row was stored, ``False`` when the identity existed.
    """
    result = db.execute(
        pg_insert(activity_models.ActivitySource)
        .values(
            id=uuid.uuid4(),
            activity_id=activity_id,
            user_id=user_id,
            kind=source.kind,
            provider_id=source.provider_id,
            file_sha256=source.file_sha256,
            session_start=source.session_start,
            precedence=source.precedence,
        )
        .on_conflict_do_nothing()
        .returning(activity_models.ActivitySource.id)
    )
    return result.first() is not None


def delete_for_activities(activity_ids: Sequence[uuid.UUID], db: Session) -> None:
    """Stage the deletion of every source of the given activities.

    Args:
        activity_ids: The activities.
        db: Database session; the caller commits.
    """
    if not activity_ids:
        return
    db.execute(
        sa_delete(activity_models.ActivitySource).where(activity_models.ActivitySource.activity_id.in_(activity_ids))
    )
    db.flush()


def delete_strava_sources_for_user(user_id: uuid.UUID, db: Session) -> int:
    """Stage the deletion of every Strava source a user has.

    Args:
        user_id: The owner.
        db: Database session; the caller commits.

    Returns:
        The number of rows deleted.
    """
    deleted = core_database.rowcount(
        db,
        sa_delete(activity_models.ActivitySource).where(
            activity_models.ActivitySource.user_id == user_id,
            activity_models.ActivitySource.kind == activity_constants.SOURCE_KIND_STRAVA,
        ),
    )
    db.flush()
    return deleted


def list_for_activities(activity_ids: Sequence[uuid.UUID], db: Session) -> list[activity_contracts.SourceRead]:
    """Read the sources of the given activities.

    Args:
        activity_ids: The activities.
        db: Database session.

    Returns:
        The sources, oldest first, for the profile export.
    """
    if not activity_ids:
        return []
    rows = db.scalars(
        select(activity_models.ActivitySource)
        .where(activity_models.ActivitySource.activity_id.in_(activity_ids))
        .order_by(activity_models.ActivitySource.received_at, activity_models.ActivitySource.id)
    ).all()
    return [
        activity_contracts.SourceRead(
            activity_id=row.activity_id,
            kind=row.kind,
            provider_id=row.provider_id,
            file_sha256=row.file_sha256,
            session_start=row.session_start,
            precedence=row.precedence,
            received_at=row.received_at,
        )
        for row in rows
    ]


def floor_to_second(start: datetime) -> datetime:
    """Drop the sub-second part of a start, the precision a source's recording start is kept at.

    Args:
        start: An aware start time.

    Returns:
        The start in whole seconds.
    """
    return start.replace(microsecond=0)


def lock_user_matching(user_id: uuid.UUID, db: Session) -> None:
    """Take the user's matching lock until the transaction ends.

    Two imports of one user that are about to look for the same effort take turns: the second finds what the first
    stored. The lock is held in the database, so it holds across replicas, and ends with the transaction.

    Args:
        user_id: The owner whose imports take turns.
        db: Database session, in the transaction that matches and stores.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('activity_match:' || :user_id, 0))"),
        {"user_id": str(user_id)},
    )


def set_file_source_precedence(activity_id: uuid.UUID, file_sha256: str, precedence: int, db: Session) -> None:
    """Stage the precedence of an activity's file source of the given content.

    Args:
        activity_id: The activity.
        file_sha256: Hex SHA-256 of the file the source identifies.
        precedence: The precedence the file's format earns.
        db: Database session; the caller commits.
    """
    db.execute(
        sa_update(activity_models.ActivitySource)
        .where(
            activity_models.ActivitySource.activity_id == activity_id,
            activity_models.ActivitySource.kind == activity_constants.SOURCE_KIND_FILE,
            activity_models.ActivitySource.file_sha256 == file_sha256,
        )
        .values(precedence=precedence)
    )
    db.flush()


def best_precedences(activity_ids: Sequence[uuid.UUID], db: Session) -> dict[uuid.UUID, int]:
    """Read the best precedence among the sources of each of the given activities.

    Args:
        activity_ids: The activities.
        db: Database session.

    Returns:
        The best precedence by activity; an activity with no source is absent.
    """
    if not activity_ids:
        return {}
    rows = db.execute(
        select(activity_models.ActivitySource.activity_id, func.max(activity_models.ActivitySource.precedence))
        .where(activity_models.ActivitySource.activity_id.in_(activity_ids))
        .group_by(activity_models.ActivitySource.activity_id)
    ).all()
    return {activity_id: precedence for activity_id, precedence in rows}
