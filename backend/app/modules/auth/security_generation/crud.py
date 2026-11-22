"""Persistence operations for account security generations."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import modules.auth.security_generation.models as security_generation_models

_Model = security_generation_models.AccountSecurityGeneration


def read(user_id: uuid.UUID, db: Session) -> int:
    """Return the user's generation without creating or locking its row.

    Args:
        user_id: ID of the user.
        db: SQLAlchemy session.

    Returns:
        The generation; 0 for an account that has never had a security change.
    """
    generation = db.execute(select(_Model.generation).where(_Model.user_id == user_id)).scalar_one_or_none()
    return 0 if generation is None else generation


def bump(user_id: uuid.UUID, db: Session) -> None:
    """Stage the advance of the user's generation by one, creating the row at 1 when there is none.

    Args:
        user_id: ID of the user.
        db: SQLAlchemy session.
    """
    stmt = insert(_Model).values(user_id=user_id, generation=1)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={"generation": _Model.generation + 1, "updated_at": func.now()},
        )
    )
    db.flush()


def lock(user_id: uuid.UUID, db: Session) -> int:
    """Return the user's generation and hold its row lock until the transaction ends, creating the row at 0.

    The row is created when missing, so there is always a row to lock: a concurrent bump of the same user waits on
    the lock, or the lock waits on the bump.

    Args:
        user_id: ID of the user.
        db: SQLAlchemy session.

    Returns:
        The generation; 0 for an account that has never had a security change.
    """
    db.execute(insert(_Model).values(user_id=user_id, generation=0).on_conflict_do_nothing(index_elements=["user_id"]))
    return db.execute(select(_Model.generation).where(_Model.user_id == user_id).with_for_update()).scalar_one()
