"""Storage and refresh of the identity-provider refresh token each SSO session holds."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import jasil.audit as jasil_audit
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.refresh_claim_store as idp_refresh_claim_store
import modules.auth.identity_providers.token_policy as token_policy
import modules.auth.sessions.audit_actions as sessions_audit_actions
import modules.auth.sessions.integration_service as sessions_integration

logger = core_logger.get_logger(__name__)

DEFAULT_TOKEN_EXPIRY_SECONDS = 300


class IdpTokenService:
    """Own the lifecycle of the identity-provider refresh token each SSO session holds."""

    def __init__(self, oidc: oidc_client_service.OidcClientService) -> None:
        """Initialize the service with the client that reaches the providers."""
        self._oidc = oidc

    def request_idp_token_refresh(self, user_id: int, session_id: str, db: Session) -> None:
        """Clear the session's identity-provider token if policy retires it, or queue its refresh if it is expiring.

        Runs inside a request, so it makes no provider call: the refresh itself is an event handled by
        :meth:`refresh_idp_tokens` on a worker. The event is published when the caller commits.

        Args:
            user_id: The session's user.
            session_id: The session that was just refreshed.
            db: Database session holding the caller's transaction.
        """
        session_token = identity_provider_links_integration.get_idp_session_token(session_id, db)
        if session_token is None or session_token.refresh_token is None:
            return
        action = token_policy.should_refresh_idp_token(session_token)
        if action is token_policy.TokenAction.REFRESH:
            idp_event_publishers.publish_idp_token_refresh_requested(user_id, session_id, db)
        elif action is token_policy.TokenAction.CLEAR:
            identity_provider_links_integration.clear_idp_session_refresh_token_if_unchanged(
                session_id, session_token.refresh_token, db
            )

    def refresh_idp_tokens(
        self, user_id: int, session_id: str, claims: idp_refresh_claim_store.IdpRefreshClaimStore
    ) -> None:
        """Refresh the session's identity-provider token if it is about to expire. Blocking; run it on a worker.

        The sign-in is read in a short session that closes before the provider is called. A refresh that fails
        with a domain error (disabled or misconfigured provider, unreachable discovery document) or a database
        error is logged; any other error propagates.

        Args:
            user_id: The session's user.
            session_id: The session whose token to refresh.
            claims: The shared claims that keep one refresh of a session's token running at a time.
        """
        with core_database.SessionLocal() as db:
            session_token = identity_provider_links_integration.get_idp_session_token(session_id, db)
        if session_token is None:
            return
        try:
            if token_policy.should_refresh_idp_token(session_token) is token_policy.TokenAction.REFRESH:
                self.refresh_idp_session(session_id, claims)
        except (core_exceptions.DomainError, SQLAlchemyError) as err:
            logger.warning(
                "Could not refresh identity-provider token",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=session_token.idp_id),
            )

    @staticmethod
    def store_session_tokens(
        session_id: str,
        user_id: int,
        idp_id: int,
        token_response: dict[str, Any],
        db: Session,
        *,
        idp_sid: str | None,
    ) -> None:
        """Stage the identity-provider sign-in behind a new session, with its refresh and ID tokens when issued.

        The row is staged even when the provider issued no refresh token, or a token cannot be encrypted, so it
        always records which provider the session signed in through; the caller commits it with the session.

        Args:
            session_id: The session the sign-in created.
            user_id: The signed-in user.
            idp_id: The identity provider.
            token_response: The OAuth token response from the IdP containing access_token, refresh_token
                (optional), id_token (optional), and expires_in.
            db: The database session holding the session's transaction.
            idp_sid: The provider session id (``sid``) of the verified ID token, which a back-channel logout names;
                None when it named none.

        Raises:
            ValueError: If ``expires_in`` is present but not an integer or numeric string.
            SQLAlchemyError: If staging the row fails; the caller's transaction is then unusable and the error
                is left to it.

        Security Note:
            - The refresh and ID tokens are encrypted using Fernet before storage
            - If encryption fails, the error is logged, that token is not stored and authentication continues
        """
        encrypted_refresh, expires_at = IdpTokenService._encrypt_token_response(user_id, idp_id, token_response)
        identity_provider_links_integration.create_idp_session_token(
            session_id,
            user_id,
            idp_id,
            encrypted_refresh,
            expires_at,
            db,
            encrypted_id_token=IdpTokenService._encrypt_id_token(user_id, idp_id, token_response),
            idp_sid=idp_sid,
        )

    @staticmethod
    def _encrypt_id_token(user_id: int, idp_id: int, token_response: dict[str, Any]) -> str | None:
        """Encrypt the ID token of a token response, which RP-initiated logout presents as the hint.

        Args:
            user_id: The user the token belongs to, for the log.
            idp_id: The provider, for the log.
            token_response: The OAuth token response.

        Returns:
            The encrypted ID token, or None when the provider issued none or it cannot be encrypted.
        """
        id_token = token_response.get("id_token")
        if not id_token or not isinstance(id_token, str):
            return None
        try:
            return core_cryptography.encrypt_token_fernet(id_token)
        except core_exceptions.CryptographyError as err:
            logger.error(
                "Error encrypting the IdP ID token for user <user_id>, idp <idp_id>; it is not stored",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None

    @staticmethod
    def _encrypt_token_response(
        user_id: int, idp_id: int, token_response: dict[str, Any]
    ) -> tuple[str, datetime] | tuple[None, None]:
        """Encrypt the refresh token of a token response and work out when its access token expires.

        Args:
            user_id: The user the token belongs to, for the log.
            idp_id: The provider, for the log.
            token_response: The OAuth token response.

        Returns:
            The encrypted refresh token and the access-token expiry, or ``(None, None)`` when the provider issued
            no refresh token or it cannot be encrypted.

        Raises:
            ValueError: If ``expires_in`` is present but not an integer or numeric string.
        """
        refresh_token = token_response.get("refresh_token")
        if not refresh_token:
            logger.debug(
                "No refresh token provided by IdP (user_id=<user_id>, idp_id=<idp_id>). "
                "User will need to re-authenticate when session expires.",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None, None
        try:
            encrypted_refresh = core_cryptography.encrypt_token_fernet(refresh_token)
        except core_exceptions.CryptographyError as err:
            logger.error(
                "Error encrypting the IdP refresh token for user <user_id>, idp <idp_id>; it is not stored",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None, None
        # authlib accepts expires_in as a number or a numeric string, and leaves it as the provider sent it
        expires_in = token_response.get("expires_in")
        expires_in_seconds = DEFAULT_TOKEN_EXPIRY_SECONDS if expires_in is None else int(expires_in)
        return encrypted_refresh, datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

    def _store_refreshed_token(
        self,
        session_id: str,
        user_id: int,
        idp_id: int,
        token_response: dict[str, Any],
        expected_refresh_token: str,
        db: Session,
    ) -> None:
        """Stage the token a refresh returned, only while the session still holds the token the refresh read.

        A slower refresh therefore never overwrites a newer token. A response with no refresh token stores nothing.
        A new ID token in the response replaces the stored one; without one the stored ID token stays.

        Args:
            session_id: The refreshed session.
            user_id: The session's user.
            idp_id: The identity provider.
            token_response: The OAuth token response of the refresh.
            expected_refresh_token: The encrypted token the refresh read.
            db: The database session for storing the token.

        Raises:
            ValueError: If ``expires_in`` is present but not an integer or numeric string.
            SQLAlchemyError: If staging the token fails.
        """
        encrypted_refresh, expires_at = self._encrypt_token_response(user_id, idp_id, token_response)
        if encrypted_refresh is None or expires_at is None:
            return
        if not identity_provider_links_integration.replace_idp_session_token_if_unchanged(
            session_id,
            expected_refresh_token,
            encrypted_refresh,
            expires_at,
            db,
            encrypted_id_token=self._encrypt_id_token(user_id, idp_id, token_response),
        ):
            logger.debug(
                "Kept the IdP refresh token another refresh stored for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return
        logger.debug(
            "Stored IdP refresh token for user <user_id>, idp <idp_id> (expires at <value_3>)",
            extra=core_logger.context(user_id=user_id, idp_id=idp_id, value_3=expires_at.isoformat()),
        )

    def refresh_idp_session(
        self,
        session_id: str,
        claims: idp_refresh_claim_store.IdpRefreshClaimStore,
    ) -> dict[str, Any] | None:
        """Refresh one session's IdP token unless another refresh of that session is running.

        Two refreshes would present the same refresh token to the provider, which a rotating provider rejects
        and one with reuse detection punishes by revoking the session, so the session is claimed first.

        Args:
            session_id: The session whose token to refresh.
            claims: The shared claims that keep one refresh of a session's token running at a time.

        Returns:
            The new token response, or None if another refresh holds the session or this one failed.

        Raises:
            domain error: If the IdP is not found, disabled, or misconfigured, or the encryption key cannot
                be loaded (``CryptographyError``, which keeps the stored token).
        """
        if not claims.claim(session_id):
            logger.debug(
                "Skipped an IdP refresh another worker is running for session <session>",
                extra=core_logger.context(session=core_hashing.log_fingerprint(session_id)),
            )
            return None
        try:
            return self._refresh_claimed_session(session_id)
        finally:
            claims.release(session_id)

    def _refresh_claimed_session(self, session_id: str) -> dict[str, Any] | None:
        """Exchange a session's stored refresh token with the IdP for new tokens and store them.

        The provider is called with no database session open: the stored token is read in one
        short session and the outcome written in another, each committed.

        Args:
            session_id: The session whose token to refresh.

        Returns:
            The new token response if successful, or None if the refresh failed (refused or undecryptable token,
            network error, malformed token response) or the session no longer holds a token.

        Raises:
            domain error: If the IdP is not found, disabled, or misconfigured, or the encryption key cannot
                be loaded (``CryptographyError``, which keeps the stored token).
            SQLAlchemyError: If reading or writing the session's sign-in fails.

        Security Notes:
            - Refresh token is decrypted only in memory, never logged
            - If the provider refuses the token (``invalid_grant``), the Endurain session ends, unless another
              refresh replaced the token meanwhile
            - If the token cannot be decrypted, the stored token is cleared and the session lives on
            - The new token is stored only over the token this refresh read
            - Network errors do not clear the token (IdP may be temporarily down)
        """
        with core_database.SessionLocal() as db:
            session_token = identity_provider_links_integration.get_idp_session_token(session_id, db)
            if session_token is None:
                return None
            user_id = session_token.user_id
            idp_id = session_token.idp_id
            encrypted_refresh_token = session_token.refresh_token
            idp = idp_crud.get_identity_provider(idp_id, db)
        if not idp or not idp.enabled:
            raise core_exceptions.NotFoundError(f"Identity provider (ID: {idp_id}) not found or disabled")

        if not encrypted_refresh_token:
            logger.debug(
                "No refresh token stored for user <user_id>, idp <idp_id>. Cannot refresh session.",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None

        # A key that cannot be loaded raises CryptographyError, which propagates and keeps the token;
        # only a token the key cannot decrypt, or one that decrypts to nothing, is cleared.
        try:
            refresh_token = core_cryptography.decrypt_token_fernet(encrypted_refresh_token)
            if not refresh_token:
                raise core_exceptions.UndecryptableError()
        except core_exceptions.UndecryptableError as err:
            logger.warning(
                "Failed to decrypt refresh token for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            self._clear_refresh_token(session_id, user_id, idp_id, encrypted_refresh_token)
            return None

        # Resolve endpoints and credentials using helper methods
        token_endpoint = self._oidc.resolve_token_endpoint(idp)
        client_id = self._oidc.decrypt_client_id(idp)
        client_secret = self._oidc.decrypt_client_secret(idp)

        # Create OAuth client for token refresh
        client: OAuth2Client | None = None
        try:
            client = self._oidc.create_oauth_client(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=None,  # Not needed for refresh token flow
            )

            # Exchange refresh token for new tokens
            token_response = client.fetch_token(
                token_endpoint,
                grant_type="refresh_token",
                refresh_token=refresh_token,
            )

            logger.debug(
                "Successfully refreshed IdP session for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )

            # Store the new tokens (they may include a new refresh token)
            with core_database.SessionLocal() as db:
                self._store_refreshed_token(session_id, user_id, idp_id, token_response, encrypted_refresh_token, db)
                db.commit()

            return token_response

        except httpx2.TimeoutException as err:
            logger.warning(
                "Timeout refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            # Don't clear token - IdP may be temporarily down
            return None

        except httpx2.HTTPStatusError as err:
            # authlib raises this only for a 5xx answer: the provider is failing, so the token is kept.
            logger.warning(
                "HTTP error refreshing IdP session for user <user_id>, idp <idp_id>: <status_code>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, status_code=err.response.status_code),
            )
            return None

        except httpx2.RequestError as err:
            logger.warning(
                "Network error refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            # Don't clear token - network issue, not token issue
            return None

        except OAuthError as err:
            if err.error == "invalid_grant":
                logger.warning(
                    "IdP refresh token invalid/revoked for user <user_id>, idp <idp_id>: <error>",
                    extra=core_logger.context(user_id=user_id, idp_id=idp_id, error=err.error),
                )
                self._end_refused_session(session_id, user_id, idp_id, encrypted_refresh_token)
                return None
            logger.warning(
                "IdP refused the session refresh for user <user_id>, idp <idp_id>: <error>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, error=err.error),
            )
            return None

        except (ValueError, TypeError, OverflowError, httpx2.InvalidURL) as err:
            # A malformed token response (a non-JSON body, or an expires_in that is not a number or is out of
            # range), or a token endpoint URL httpx cannot send to, says nothing about the stored token, so it is kept.
            logger.warning(
                "Malformed token response refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            return None
        finally:
            if client is not None:
                client.close()

    @staticmethod
    def _clear_refresh_token(session_id: str, user_id: int, idp_id: int, expected_refresh_token: str) -> bool:
        """Clear the refresh token a refresh read, in a session of its own, unless the session holds another now.

        Args:
            session_id: The session whose token to clear.
            user_id: The session's user, for the log.
            idp_id: The provider the token belongs to, for the log.
            expected_refresh_token: The encrypted token the refresh read.

        Returns:
            True when the token was cleared, False when the session holds another one now.
        """
        with core_database.SessionLocal() as db:
            cleared = identity_provider_links_integration.clear_idp_session_refresh_token_if_unchanged(
                session_id, expected_refresh_token, db
            )
            db.commit()
        if not cleared:
            logger.debug(
                "Kept the IdP refresh token another refresh stored for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return False
        logger.info(
            "Cleared the identity-provider refresh token for user <user_id>, idp <idp_id>",
            extra=core_logger.context(user_id=user_id, idp_id=idp_id),
        )
        return True

    def _end_refused_session(self, session_id: str, user_id: int, idp_id: int, expected_refresh_token: str) -> None:
        """End the Endurain session whose refresh token the provider refused, and audit it.

        The rejected token is cleared first, which fails when another refresh replaced it meanwhile; the session
        then lives on. The session ends through the sessions surface, which publishes the revocation.

        Args:
            session_id: The session whose token the provider refused.
            user_id: The session's user.
            idp_id: The provider that refused it, for the log.
            expected_refresh_token: The encrypted token the refresh read.
        """
        if not self._clear_refresh_token(session_id, user_id, idp_id, expected_refresh_token):
            return
        with core_database.SessionLocal() as db:
            try:
                sessions_integration.delete_session(session_id, user_id, db)
            except core_exceptions.NotFoundError:
                logger.debug(
                    "The session whose IdP token was refused had already ended for user <user_id>",
                    extra=core_logger.context(user_id=user_id),
                )
                return
            jasil_audit.stage(
                db,
                sessions_audit_actions.SESSION_REVOKE,
                target_type="session",
                target_id=session_id,
                target_owner_id=str(user_id),
                details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=1),
            )
            db.commit()
        logger.info(
            "Ended the session whose identity-provider token was refused for user <user_id>, idp <idp_id>",
            extra=core_logger.context(user_id=user_id, idp_id=idp_id),
        )
