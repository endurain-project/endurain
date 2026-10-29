"""Refresh-token reuse operations exposed to auth peers."""

from datetime import datetime

from sqlalchemy.orm import Session

import modules.auth.rotated_refresh_tokens.service as rotated_token_service


def store_rotated_token(
    raw_token: str,
    token_family_id: str,
    rotation_count: int,
    db: Session,
    *,
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
        refresh_token_exp=refresh_token_exp,
        replacement_refresh_token=replacement_refresh_token,
        replacement_refresh_token_exp=replacement_refresh_token_exp,
    )


def check_token_reuse(raw_token: str, db: Session) -> tuple[bool, bool]:
    """Check whether a refresh token has already been rotated."""
    return rotated_token_service.check_token_reuse(raw_token, db)


def get_grace_replay_token(raw_token: str, db: Session) -> tuple[str, datetime] | None:
    """Return the replacement token for a retry inside the grace period."""
    return rotated_token_service.get_grace_replay_token(raw_token, db)


def delete_by_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of rotated-token records in a family."""
    return rotated_token_service.delete_by_family(token_family_id, db)
