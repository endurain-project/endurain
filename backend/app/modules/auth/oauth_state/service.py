"""OAuth-state cleanup orchestration."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.oauth_state.crud as oauth_state_crud


def delete_expired_oauth_states(db: Session) -> int:
    """Delete expired OAuth states, one batch per commit."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(
        lambda limit: oauth_state_crud.delete_expired_oauth_states(now, limit, db), db
    )
