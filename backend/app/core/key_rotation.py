"""Re-encryption of stored secrets after the Fernet key list changes.

Each module that owns an encrypted column stages batches through :func:`stage_reencrypt_batch` (or its own
variant for a nested value) and runs them with :func:`reencrypt_in_batches`, which does nothing while a single
key is configured.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import InstrumentedAttribute, Session

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

#: Rows read, and written, per transaction.
BATCH_SIZE = 100


@dataclass(frozen=True)
class RotationCounts:
    """How many stored values a rotation rewrote and how many no configured key decrypts."""

    rotated: int = 0
    undecryptable: int = 0

    def __add__(self, other: "RotationCounts") -> "RotationCounts":
        """Sum two counts."""
        return RotationCounts(self.rotated + other.rotated, self.undecryptable + other.undecryptable)


@dataclass(frozen=True)
class BatchResult[K]:
    """One staged batch: the last id it read (None when no row followed the cursor) and its counts."""

    last_id: K | None
    counts: RotationCounts = RotationCounts()


def stage_reencrypt_batch[K](
    model: type[core_database.Base],
    id_column: InstrumentedAttribute[K],
    columns: Sequence[InstrumentedAttribute[str | None]],
    after_id: K | None,
    limit: int,
    db: Session,
) -> BatchResult[K]:
    """Stage the re-encryption of up to ``limit`` rows after ``after_id``, ordered by id (flushed, not committed).

    A value is rewritten only while it still holds the ciphertext that was read, so a write that lands between
    the read and the update is never overwritten. A value no configured key decrypts is left as it is.

    Args:
        model: The ORM model that owns the columns.
        id_column: The model's primary key.
        columns: The model's encrypted string columns.
        after_id: Keyset cursor; only rows with a greater id are read, and None reads from the first row.
        limit: Maximum number of rows to read.
        db: SQLAlchemy database session.

    Returns:
        The last id read and the values rewritten or left undecryptable.
    """
    query = select(id_column, *columns)
    if after_id is not None:
        query = query.where(id_column > after_id)
    rows = db.execute(query.order_by(id_column).limit(limit)).all()
    rotated = undecryptable = 0
    for row_id, *values in rows:
        for column, old in zip(columns, values, strict=True):
            if old is None:
                continue
            try:
                new = core_cryptography.reencrypt_to_primary_key(old)
            except core_exceptions.UndecryptableError:
                undecryptable += 1
                continue
            if new is not None:
                rotated += core_database.rowcount(
                    db, update(model).where(id_column == row_id, column == old).values({column.key: new})
                )
    return BatchResult(rows[-1][0] if rows else None, RotationCounts(rotated, undecryptable))


def reencrypt_in_batches[K](
    label: str, stage_batch: Callable[[K | None, int], BatchResult[K]], db: Session
) -> RotationCounts:
    """Re-encrypt a module's stored secrets one bounded batch per transaction.

    Does nothing while only one key is configured. Logs the counts, never a value.

    Args:
        label: What the batches belong to, for the log line.
        stage_batch: Stages the batch after the given id (None for the first batch) with the given limit.
        db: The session the batches run and commit in.

    Returns:
        The values rewritten and the values no configured key decrypts.
    """
    total = RotationCounts()
    if not core_cryptography.has_older_keys():
        return total
    after_id: K | None = None
    while True:
        batch = stage_batch(after_id, BATCH_SIZE)
        db.commit()
        total += batch.counts
        if batch.last_id is None:
            break
        after_id = batch.last_id
    logger.info(
        "Re-encrypted stored secrets under the first FERNET_KEY",
        extra=core_logger.context(module=label, rotated=total.rotated, undecryptable=total.undecryptable),
    )
    return total
