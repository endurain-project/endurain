"""OAuth-state cleanup orchestration."""

from sqlalchemy.orm import Session

import modules.auth.oauth_state.crud as oauth_state_crud


def delete_expired_oauth_states(db: Session) -> int:
    """Stage removal of expired OAuth states."""
    return oauth_state_crud.delete_expired_oauth_states(db)
