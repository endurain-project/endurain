"""What an identity-provider sign-in to an existing account writes to it, held until the sign-in completes.

The callback writes nothing to an existing account: the account may still need its second factor. It stages the
link to create, the claims to sync and the last-login stamp under the session it creates, and the completion of that
session applies them in the transaction that claims the session. A record lives no longer than the session's exchange
window, in the platform ``StateProvider`` under the digest of the session id, Fernet-encrypted because it holds the
provider's subject, name and email.
"""

import uuid

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import ValidationError

import core.attempt_state as core_attempt_state
import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.identity_providers.contracts as idp_contracts

logger = core_logger.get_logger(__name__)


def _record_key(session_id: uuid.UUID) -> str:
    """Build the storage key of a session's staged sign-in from the digest of the session id.

    Args:
        session_id: The session the callback created.

    Returns:
        The storage key.
    """
    return core_attempt_state.key("sso_sign_in", "staged", core_hashing.sha256_hex(str(session_id)))


class StagedSignInStore:
    """Staged sign-ins backed by the platform ``StateProvider``; staging and reading fail closed on an outage."""

    def __init__(self, state: StateProvider) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider, resolved at the entry point.
        """
        self._state = state

    def stage(self, session_id: uuid.UUID, staged: idp_contracts.StagedSignIn, *, ttl_seconds: int) -> None:
        """Store what a session's completion applies, encrypted, for as long as the session can be exchanged.

        Args:
            session_id: The session the callback created.
            staged: What the completion applies to the account.
            ttl_seconds: Seconds until the session's exchange window ends.

        Raises:
            StateUnavailableError: When the state store is unavailable.
            CryptographyError: When the record cannot be encrypted.
        """
        payload = core_cryptography.encrypt_token_fernet(staged.model_dump_json())
        try:
            self._state.set(_record_key(session_id), payload.encode(), ttl_seconds=ttl_seconds)
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("stage_sso_sign_in", err)

    def read(self, session_id: uuid.UUID) -> idp_contracts.StagedSignIn | None:
        """Return a session's staged sign-in without removing it.

        Args:
            session_id: The session being completed.

        Returns:
            The staged sign-in, or ``None`` when none is stored, it expired, or it cannot be decrypted or read.

        Raises:
            StateUnavailableError: When the state store is unavailable.
        """
        try:
            stored = self._state.get(_record_key(session_id))
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("read_sso_sign_in", err)
        if stored is None:
            return None
        try:
            return idp_contracts.StagedSignIn.model_validate_json(
                core_cryptography.decrypt_token_fernet(stored.decode())
            )
        except core_exceptions.CryptographyError, ValidationError:
            logger.warning("A staged SSO sign-in could not be read")
            return None

    def discard(self, session_id: uuid.UUID) -> None:
        """Remove a session's staged sign-in once its completion committed.

        An outage is logged and the record left to expire with the exchange window: the session's claim is one-shot,
        so nothing can apply the record again.

        Args:
            session_id: The session that completed.
        """
        try:
            self._state.delete(_record_key(session_id))
        except StateBackendUnavailableError as err:
            logger.warning("A staged SSO sign-in was left to expire: the state store is unavailable", exc_info=err)
