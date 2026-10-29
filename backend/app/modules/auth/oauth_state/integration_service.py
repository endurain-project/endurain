"""OAuth-state operations exposed to auth peers."""

from sqlalchemy.orm import Session

import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.oauth_state.utils as oauth_state_utils


def create_oauth_state(
    state_id: str,
    nonce: str,
    client_type: str,
    ip_address: str | None,
    db: Session,
    *,
    idp_id: int | None = None,
    redirect_path: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    user_id: int | None = None,
    browser_binding_hash: str | None = None,
    idp_code_verifier: str | None = None,
) -> oauth_state_schema.OAuthStateRead:
    """Stage an OAuth-state row."""
    return oauth_state_crud.create_oauth_state(
        state_id,
        nonce,
        client_type,
        ip_address,
        db,
        idp_id=idp_id,
        redirect_path=redirect_path,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_id=user_id,
        browser_binding_hash=browser_binding_hash,
        idp_code_verifier=idp_code_verifier,
    )


def get_oauth_state_by_id_and_not_used(state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
    """Return an unused, unexpired OAuth state."""
    return oauth_state_crud.get_oauth_state_by_id_and_not_used(state_id, db)


def get_oauth_state_by_id_not_expired(state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
    """Return an unexpired OAuth state."""
    return oauth_state_crud.get_oauth_state_by_id_not_expired(state_id, db)


def mark_oauth_state_used(state_id: str, db: Session) -> bool:
    """Stage an OAuth-state claim."""
    return oauth_state_crud.mark_oauth_state_used(state_id, db)


def delete_oauth_state(oauth_state_id: str, db: Session) -> int:
    """Stage OAuth-state deletion."""
    return oauth_state_crud.delete_oauth_state(oauth_state_id, db)


def create_state_id_and_nonce() -> tuple[str, str]:
    """Generate random state and nonce values."""
    return oauth_state_utils.create_state_id_and_nonce()
