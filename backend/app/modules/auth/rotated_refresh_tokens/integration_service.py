"""Refresh-token reuse operations exposed to auth peers."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

import modules.auth.rotated_refresh_tokens.service as rotated_token_service


def store_rotated_token(
    raw_token: str,
    token_family_id: uuid.UUID,
    rotation_count: int,
    db: Session,
    *,
    ip_address: str,
    user_agent: str,
    refresh_token_exp: datetime,
    replacement_refresh_token: str,
    replacement_refresh_token_exp: datetime,
) -> None:
    """Stage a rotated refresh-token record."""
    rotated_token_service.store_rotated_token(
        raw_token,
        token_family_id,
        rotation_count,
        db,
        ip_address=ip_address,
        user_agent=user_agent,
        refresh_token_exp=refresh_token_exp,
        replacement_refresh_token=replacement_refresh_token,
        replacement_refresh_token_exp=replacement_refresh_token_exp,
    )


def check_token_reuse(raw_token: str, db: Session, *, ip_address: str, user_agent: str) -> tuple[bool, bool]:
    """Check whether a refresh token has already been rotated and whether the rotating client presents it."""
    return rotated_token_service.check_token_reuse(raw_token, db, ip_address=ip_address, user_agent=user_agent)


def get_grace_replay_token(
    raw_token: str, db: Session, *, ip_address: str, user_agent: str
) -> tuple[str, datetime] | None:
    """Return the replacement token for a retry inside the grace period from the rotating client."""
    return rotated_token_service.get_grace_replay_token(raw_token, db, ip_address=ip_address, user_agent=user_agent)


def delete_by_family(token_family_id: uuid.UUID, db: Session) -> int:
    """Stage deletion of rotated-token records in a family."""
    return rotated_token_service.delete_by_family(token_family_id, db)
