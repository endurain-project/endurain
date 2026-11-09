"""OAuth-state cleanup orchestration."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.database as core_database
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.schema as oauth_state_schema


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
    purpose: oauth_state_constants.OAuthStatePurpose,
    session_id: str | None = None,
    action: str | None = None,
    ends_other_sessions: bool = False,
    security_generation: int | None = None,
) -> oauth_state_schema.OAuthStateRead:
    """Stage an OAuth state whose nonce and PKCE verifier are stored encrypted.

    Returns:
        The staged state with the nonce and verifier in plaintext.

    Raises:
        CryptographyError: If the secrets cannot be encrypted.
    """
    stored = oauth_state_crud.create_oauth_state(
        state_id,
        core_cryptography.encrypt_token_fernet(nonce),
        client_type,
        ip_address,
        db,
        idp_id=idp_id,
        redirect_path=redirect_path,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_id=user_id,
        browser_binding_hash=browser_binding_hash,
        idp_code_verifier=core_cryptography.encrypt_token_fernet(idp_code_verifier),
        purpose=purpose,
        session_id=session_id,
        action=action,
        ends_other_sessions=ends_other_sessions,
        security_generation=security_generation,
    )
    return _decrypted(stored)


def get_oauth_state_by_id_and_not_used(state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
    """Return an unused, unexpired OAuth state with its secrets in plaintext.

    Raises:
        CryptographyError: If a stored secret cannot be decrypted.
    """
    stored = oauth_state_crud.get_oauth_state_by_id_and_not_used(state_id, db)
    return _decrypted(stored) if stored is not None else None


def get_oauth_state_by_id_not_expired(state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
    """Return an unexpired OAuth state with its secrets in plaintext.

    Raises:
        CryptographyError: If a stored secret cannot be decrypted.
    """
    stored = oauth_state_crud.get_oauth_state_by_id_not_expired(state_id, db)
    return _decrypted(stored) if stored is not None else None


def _decrypted(state: oauth_state_schema.OAuthStateRead) -> oauth_state_schema.OAuthStateRead:
    """Return the state with its nonce and PKCE verifier decrypted."""
    return state.model_copy(
        update={
            "nonce": core_cryptography.decrypt_token_fernet(state.nonce),
            "idp_code_verifier": core_cryptography.decrypt_token_fernet(state.idp_code_verifier),
        }
    )


def delete_expired_oauth_states(db: Session) -> int:
    """Delete expired OAuth states, one batch per commit."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(
        lambda limit: oauth_state_crud.delete_expired_oauth_states(now, limit, db), db
    )
