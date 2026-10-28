"""Refresh-token reuse operations exposed to auth peers."""

from datetime import datetime

from sqlalchemy.orm import Session

import modules.auth.rotated_refresh_tokens.crud as rotated_token_crud
import modules.auth.rotated_refresh_tokens.schema as rotated_token_schema
import modules.auth.rotated_refresh_tokens.service as rotated_token_service


def hmac_hash_token(token: str) -> str:
    """Return the server-keyed digest used for rotated-token lookup."""
    return rotated_token_service.hmac_hash_token(token)


def store_rotated_token(
    raw_token: str,
    token_family_id: str,
    rotation_count: int,
    db: Session,
    *,
    replacement_refresh_token: str,
    replacement_refresh_token_exp: datetime,
) -> None:
    """Stage a rotated refresh-token record."""
    rotated_token_service.store_rotated_token(
        raw_token,
        token_family_id,
        rotation_count,
        db,
        replacement_refresh_token=replacement_refresh_token,
        replacement_refresh_token_exp=replacement_refresh_token_exp,
    )


def check_token_reuse(raw_token: str, db: Session) -> tuple[bool, bool]:
    """Check whether a refresh token has already been rotated."""
    return rotated_token_service.check_token_reuse(raw_token, db)


def get_grace_replay_token(raw_token: str, db: Session) -> tuple[str, datetime] | None:
    """Return the replacement token for a retry inside the grace period."""
    return rotated_token_service.get_grace_replay_token(raw_token, db)


def invalidate_token_family(token_family_id: str, db: Session) -> int:
    """Stage invalidation of sessions and rotated tokens in a family."""
    return rotated_token_service.invalidate_token_family(token_family_id, db)


def get_rotated_token_by_hash(hashed_token: str, db: Session) -> rotated_token_schema.RotatedRefreshTokenRead | None:
    """Return a rotated-token DTO by its keyed digest."""
    return rotated_token_crud.get_rotated_token_by_hash(hashed_token, db)
