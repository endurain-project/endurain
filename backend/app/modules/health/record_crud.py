"""Persistence steps the health packages run identically on their per-user records.

A package describes its record once with a :class:`RecordSpec` and its ``crud`` delegates the steps that
do not depend on the record type: load by id and owner, count, page, create, edit with the ``If-Match``
check, and delete. It owns no table: the model and the schemas are the caller's. Like every ``crud`` it
stages writes with ``flush`` and never commits.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.computation as health_computation

#: Answer to an edit that moves a dated record onto a day that already has one.
DATE_TAKEN_MESSAGE = "Another record already exists for that date"


class _Row(Protocol):
    """A stored, versioned record that belongs to a user."""

    id: int
    user_id: int
    version: int


@dataclass(frozen=True)
class RecordSpec:
    """What the shared steps need to know about one record type.

    Attributes:
        model: The record's ORM class.
        read_schema: The schema a row is returned as.
        not_found: The detail of the error for a record the user does not have.
        etag_label: How a stale ``If-Match`` names the record.
    """

    model: type[_Row]
    read_schema: type[BaseModel]
    not_found: str
    etag_label: str


def duplicate_date_message(day: date | None) -> str:
    """Build the detail of the error for a second record on a day.

    Args:
        day: The day that already has a record.

    Returns:
        The error detail.
    """
    return f"Duplicate entry error. Check if there is already an entry created for {day}"


def get_owned(spec: RecordSpec, record_id: int, user_id: int, db: Session) -> _Row:
    """Load a user's row by id.

    Args:
        spec: The record type.
        record_id: The record to load.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The ORM row.

    Raises:
        NotFoundError: If the user has no such record.
    """
    row = db.execute(health_computation.owned_record_statement(spec.model, record_id, user_id)).scalar_one_or_none()
    if row is None:
        raise core_exceptions.NotFoundError(spec.not_found)
    return row


def exists(spec: RecordSpec, record_id: int, user_id: int, db: Session) -> bool:
    """Report whether a user has a record.

    Args:
        spec: The record type.
        record_id: The record to look for.
        user_id: The record's owner.
        db: Database session.

    Returns:
        True when the user has such a record.
    """
    return bool(db.execute(health_computation.owned_record_exists_statement(spec.model, record_id, user_id)).scalar())


def find_by_id(spec: RecordSpec, record_id: int, user_id: int, db: Session) -> BaseModel | None:
    """Retrieve a user's record by id.

    Args:
        spec: The record type.
        record_id: The record to fetch.
        user_id: The record's owner.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = health_computation.owned_record_statement(spec.model, record_id, user_id)
    row = db.execute(stmt).scalar_one_or_none()
    return health_computation.to_read_schema(spec.read_schema, row) if row else None


def find_by_date(spec: RecordSpec, user_id: int, day: str, db: Session) -> BaseModel | None:
    """Retrieve a user's record for a date, for a record type that has one per day.

    Args:
        spec: The record type; its model has a ``date`` column.
        user_id: The record's owner.
        day: The record's date.
        db: Database session.

    Returns:
        The record, or ``None``.
    """
    stmt = select(spec.model).where(spec.model.date == func.date(day), spec.model.user_id == user_id)
    row = db.execute(stmt).scalar_one_or_none()
    return health_computation.to_read_schema(spec.read_schema, row) if row else None


def count(spec: RecordSpec, user_id: int, since_column: ColumnElement, since: date | None, db: Session) -> int:
    """Count a user's records.

    Args:
        spec: The record type.
        user_id: The records' owner.
        since_column: The column ``since`` is compared against.
        since: Count only records whose ``since_column`` is on or after this date.
        db: Database session.

    Returns:
        The number of records.
    """
    stmt = health_computation.user_record_count_statement(spec.model, user_id, since_column, since)
    return db.execute(stmt).scalar_one()


def list_page(
    spec: RecordSpec,
    user_id: int,
    order_column: ColumnElement,
    since_column: ColumnElement,
    since: date | None,
    page_number: int | None,
    num_records: int | None,
    db: Session,
) -> list:
    """Retrieve a user's records, newest first, optionally paginated and bounded.

    Args:
        spec: The record type.
        user_id: The records' owner.
        order_column: The column the records are ordered by, descending.
        since_column: The column ``since`` is compared against.
        since: Return only records whose ``since_column`` is on or after this date.
        page_number: 1-based page; paginates only together with ``num_records``.
        num_records: Records per page.
        db: Database session.

    Returns:
        The records as ``spec.read_schema``.
    """
    stmt = health_computation.user_records_statement(
        spec.model, user_id, order_column, since_column, since, page_number, num_records
    )
    return health_computation.to_read_schemas(spec.read_schema, list(db.execute(stmt).scalars().all()))


def save(spec: RecordSpec, row: _Row, db: Session, *, conflict: str | None = None) -> BaseModel:
    """Flush a changed row and read it back.

    Args:
        spec: The record type.
        row: The row whose changes are staged.
        db: Database session.
        conflict: The detail of the ``ConflictError`` raised when the change violates a constraint;
            ``None`` lets the integrity error through.

    Returns:
        The row as ``spec.read_schema``, with the version the flush gave it.

    Raises:
        ConflictError: If ``conflict`` is given and the change violates a constraint.
    """
    try:
        db.flush()
    except IntegrityError as err:
        if conflict is None:
            raise
        raise core_exceptions.ConflictError(conflict) from err
    db.refresh(row)
    return health_computation.to_read_schema(spec.read_schema, row)


def create(spec: RecordSpec, user_id: int, record: BaseModel, db: Session, *, conflict: str) -> BaseModel:
    """Stage a new record for a user.

    Args:
        spec: The record type.
        user_id: The record's owner.
        record: The record to create.
        db: Database session.
        conflict: The detail of the error raised when the insert violates a constraint.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the insert violates a constraint.
    """
    return add(spec, spec.model(**record.model_dump(exclude_none=False), user_id=user_id), db, conflict=conflict)


def add(spec: RecordSpec, row: _Row, db: Session, *, conflict: str) -> BaseModel:
    """Stage a new row.

    Args:
        spec: The record type.
        row: The row to insert.
        db: Database session.
        conflict: The detail of the error raised when the insert violates a constraint.

    Returns:
        The staged record.

    Raises:
        ConflictError: If the insert violates a constraint.
    """
    db.add(row)
    return save(spec, row, db, conflict=conflict)


def edit_row(
    spec: RecordSpec, row: _Row, changes: BaseModel, db: Session, *, if_match: str, conflict: str | None = None
) -> BaseModel:
    """Stage the set fields of an update on a loaded row.

    Args:
        spec: The record type.
        row: The row to change.
        changes: The fields to change; fields that were not set are left alone.
        db: Database session.
        if_match: The ``If-Match`` precondition.
        conflict: The detail of the ``ConflictError`` raised when the change violates a constraint;
            ``None`` lets the integrity error through.

    Returns:
        The updated record.

    Raises:
        PreconditionFailedError: When ``if_match`` does not name the row's version.
        ConflictError: If ``conflict`` is given and the change violates a constraint.
    """
    core_etag.require_if_match(if_match, row.version, spec.etag_label)
    for key, value in changes.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    return save(spec, row, db, conflict=conflict)


def edit(
    spec: RecordSpec,
    record_id: int,
    user_id: int,
    changes: BaseModel,
    db: Session,
    *,
    if_match: str,
    conflict: str | None = None,
) -> BaseModel:
    """Stage an update to a user's record.

    Args:
        spec: The record type.
        record_id: The record to change.
        user_id: The record's owner.
        changes: The fields to change.
        db: Database session.
        if_match: The ``If-Match`` precondition.
        conflict: The detail of the ``ConflictError`` raised when the change violates a constraint;
            ``None`` lets the integrity error through.

    Returns:
        The updated record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
        ConflictError: If ``conflict`` is given and the change violates a constraint.
    """
    row = get_owned(spec, record_id, user_id, db)
    return edit_row(spec, row, changes, db, if_match=if_match, conflict=conflict)


def delete(spec: RecordSpec, record_id: int, user_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's record.

    Args:
        spec: The record type.
        record_id: The record to delete.
        user_id: The record's owner.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    row = get_owned(spec, record_id, user_id, db)
    core_etag.require_if_match(if_match, row.version, spec.etag_label)
    db.delete(row)
    db.flush()
