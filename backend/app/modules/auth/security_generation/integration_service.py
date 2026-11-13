"""Security-generation operations used by the modules that start, redeem or invalidate a proof.

A security change calls ``stage_bump`` before its other writes, and a redeem calls ``matches_locked`` before its
writes, so the generation row is always the first lock taken.
"""

import uuid

from sqlalchemy.orm import Session

import modules.auth.security_generation.crud as security_generation_crud


def current_generation(user_id: uuid.UUID, db: Session) -> int:
    """Return the account's security generation, to stamp into a proof as it is created.

    Args:
        user_id: ID of the user the proof is for.
        db: SQLAlchemy session.

    Returns:
        The current generation; 0 for an account that has never had a security change. Nothing is written, so a
        flow that stamps a proof without committing loses nothing.
    """
    return security_generation_crud.read(user_id, db)


def stage_bump(user_id: uuid.UUID, db: Session) -> None:
    """Stage the advance of the account's security generation; the caller commits.

    Every proof stamped with an earlier generation stops matching once the caller's transaction commits.

    Args:
        user_id: ID of the user whose security changed.
        db: SQLAlchemy session.
    """
    security_generation_crud.bump(user_id, db)


def matches_locked(user_id: uuid.UUID, stamped: int | None, db: Session) -> bool:
    """Return whether a proof's stamp is the account's current generation, holding the row's lock.

    The lock lasts until the caller's transaction ends, so a security change cannot commit between this check and
    the redeem it guards.

    Args:
        user_id: ID of the user the proof is for.
        stamped: The generation recorded in the proof; None for a proof created before generations existed.
        db: SQLAlchemy session.

    Returns:
        True only when the account's generation equals ``stamped``; the row is created at 0 when missing so that
        it can be locked.
    """
    if stamped is None:
        return False
    return security_generation_crud.lock(user_id, db) == stamped
