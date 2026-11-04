"""Storage, refresh and revocation of identity-provider refresh tokens."""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.refresh_claim_store as idp_refresh_claim_store
import modules.auth.identity_providers.token_policy as token_policy

logger = core_logger.get_logger(__name__)

DEFAULT_TOKEN_EXPIRY_SECONDS = 300


class IdpTokenService:
    """Own the lifecycle of the identity-provider refresh tokens stored for linked users."""

    def __init__(self, oidc: oidc_client_service.OidcClientService) -> None:
        """Initialize the service with the client that reaches the providers."""
        self._oidc = oidc

    def request_idp_token_refresh(self, user_id: int, db: Session) -> None:
        """Clear the user's identity-provider tokens that policy retires, and queue the refresh of those expiring.

        Runs inside a request, so it makes no provider call: the refresh itself is an event handled by
        :meth:`refresh_idp_tokens` on a worker. The event is published when the caller commits.

        Args:
            user_id: The user whose linked providers to assess.
            db: Database session holding the caller's transaction.
        """
        links = identity_provider_links_integration.get_user_identity_providers_by_user_id(user_id, db)
        refresh_needed = False
        for link in links:
            action = token_policy.should_refresh_idp_token(link)
            if action is token_policy.TokenAction.REFRESH:
                refresh_needed = True
            elif action is token_policy.TokenAction.CLEAR:
                identity_provider_links_integration.clear_user_identity_provider_refresh_token(user_id, link.idp_id, db)
        if refresh_needed:
            idp_event_publishers.publish_idp_token_refresh_requested(user_id, db)

    def refresh_idp_tokens(self, user_id: int, claims: idp_refresh_claim_store.IdpRefreshClaimStore) -> None:
        """Refresh the user's identity-provider tokens that are about to expire. Blocking; run it on a worker.

        The links are read in a short session that closes before any provider is called. A link whose refresh
        fails with a domain error (disabled or misconfigured provider, unreachable discovery document) or a
        database error is logged and skipped so the other links are still refreshed; any other error propagates.

        Args:
            user_id: The user whose tokens to refresh.
            claims: The shared claims that keep one refresh of a link running at a time.
        """
        with core_database.SessionLocal() as db:
            links = identity_provider_links_integration.get_user_identity_providers_by_user_id(user_id, db)
        for link in links:
            try:
                if token_policy.should_refresh_idp_token(link) is token_policy.TokenAction.REFRESH:
                    self.refresh_idp_session(user_id, link.idp_id, claims)
            except (core_exceptions.DomainError, SQLAlchemyError) as err:
                logger.warning(
                    "Could not refresh identity-provider token",
                    exc_info=err,
                    extra=core_logger.context(user_id=user_id, idp_id=link.idp_id),
                )

    def clear_all_idp_tokens(self, user_id: int, db: Session) -> None:
        """Clear locally stored IdP tokens.

        Args:
            user_id: The user whose linked providers' tokens to clear.
            db: Database session holding the caller's transaction.
        """
        links = identity_provider_links_integration.get_user_identity_providers_by_user_id(user_id, db)
        for link in links:
            identity_provider_links_integration.clear_user_identity_provider_refresh_token(user_id, link.idp_id, db)

    def store_idp_tokens(
        self,
        user_id: int,
        idp_id: int,
        token_response: dict[str, Any],
        db: Session,
        *,
        expected_refresh_token: str | None = None,
    ) -> None:
        """Store IdP tokens after successful authentication or a refresh.

        This method extracts the refresh token from the OAuth token response, encrypts it,
        and stores it along with metadata for future session renewal. If no refresh token
        is provided by the IdP, the method logs a debug message and returns gracefully.

        Args:
            user_id (int): The ID of the authenticated user.
            idp_id (int): The ID of the identity provider.
            token_response (dict[str, Any]): The OAuth token response from the IdP containing
                access_token, refresh_token (optional), and expires_in.
            db (Session): The database session for storing tokens.
            expected_refresh_token (str | None): For a refresh, the encrypted token it read: the new one is
                stored only while the link still holds it, so a slower refresh never overwrites a newer token.

        Raises:
            ValueError: If ``expires_in`` is present but not an integer or numeric string.
            SQLAlchemyError: If staging the token fails; the caller's transaction is then unusable and the
                error is left to it.

        Security Note:
            - The refresh token is encrypted using Fernet before storage
            - If encryption fails, the error is logged, nothing is stored and authentication continues
            - Missing refresh tokens are handled gracefully (not all IdPs provide them)

        Example token_response:
            {
                "access_token": "eyJhbGci...",
                "refresh_token": "eyJhbGci...",  # Optional
                "expires_in": 300,
                "token_type": "Bearer"
            }
        """
        refresh_token = token_response.get("refresh_token")

        if not refresh_token:
            logger.debug(
                "No refresh token provided by IdP (user_id=<user_id>, idp_id=<idp_id>). "
                "User will need to re-authenticate when session expires.",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return

        try:
            encrypted_refresh = core_cryptography.encrypt_token_fernet(refresh_token)
        except core_exceptions.CryptographyError as err:
            logger.error(
                "Error encrypting the IdP refresh token for user <user_id>, idp <idp_id>; it is not stored",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return

        # authlib accepts expires_in as a number or a numeric string, and leaves it as the provider sent it
        expires_in = token_response.get("expires_in")
        expires_in_seconds = DEFAULT_TOKEN_EXPIRY_SECONDS if expires_in is None else int(expires_in)
        access_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

        if expected_refresh_token is not None:
            if not identity_provider_links_integration.replace_user_identity_provider_tokens_if_unchanged(
                user_id, idp_id, expected_refresh_token, encrypted_refresh, access_token_expires_at, db
            ):
                logger.debug(
                    "Kept the IdP refresh token another refresh stored for user <user_id>, idp <idp_id>",
                    extra=core_logger.context(user_id=user_id, idp_id=idp_id),
                )
                return
        else:
            identity_provider_links_integration.store_user_identity_provider_tokens(
                user_id=user_id,
                idp_id=idp_id,
                encrypted_refresh_token=encrypted_refresh,
                access_token_expires_at=access_token_expires_at,
                db=db,
            )

        logger.debug(
            "Stored IdP refresh token for user <user_id>, idp <idp_id> (expires at <value_3>)",
            extra=core_logger.context(user_id=user_id, idp_id=idp_id, value_3=access_token_expires_at.isoformat()),
        )

    def refresh_idp_session(
        self,
        user_id: int,
        idp_id: int,
        claims: idp_refresh_claim_store.IdpRefreshClaimStore,
    ) -> dict[str, Any] | None:
        """Refresh one link's IdP session unless another refresh of that link is running.

        Two refreshes would present the same refresh token to the provider, which a rotating provider rejects
        and one with reuse detection punishes by revoking the session, so the link is claimed first.

        Args:
            user_id: The ID of the user whose session should be refreshed.
            idp_id: The ID of the identity provider.
            claims: The shared claims that keep one refresh of a link running at a time.

        Returns:
            The new token response, or None if another refresh holds the link or this one failed.

        Raises:
            domain error: If the IdP is not found, disabled, or misconfigured.
        """
        if not claims.claim(user_id, idp_id):
            logger.debug(
                "Skipped an IdP refresh another worker is running for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None
        try:
            return self._refresh_claimed_session(user_id, idp_id)
        finally:
            claims.release(user_id, idp_id)

    def _refresh_claimed_session(
        self,
        user_id: int,
        idp_id: int,
    ) -> dict[str, Any] | None:
        """Attempt to refresh a user's IdP session using stored refresh token.

        This method enables silent session renewal without re-prompting the user to login.
        It retrieves the stored encrypted refresh token, decrypts it, and exchanges it
        with the IdP for new access and refresh tokens. If successful, the new tokens
        are encrypted and stored.

        The provider is called with no database session open: the stored token is read in one
        short session and the outcome written in another, each committed.

        Args:
            user_id (int): The ID of the user whose session should be refreshed.
            idp_id (int): The ID of the identity provider.

        Returns:
            Dict[str, Any] | None: A dictionary containing the new token response if successful,
                or None if the refresh failed (expired/revoked token, network error, etc.).

        Raises:
            domain error: If the IdP is not found, disabled, or misconfigured.

        Example return value:
            {
                "access_token": "eyJhbGci...",
                "refresh_token": "eyJhbGci...",  # May be the same or new token
                "expires_in": 300,
                "token_type": "Bearer"
            }

        Security Notes:
            - Refresh token is decrypted only in memory, never logged
            - If refresh fails (invalid/revoked), the stored token is cleared, unless another refresh replaced it
            - The new token is stored only over the token this refresh read
            - Network errors do not clear the token (IdP may be temporarily down)
        """
        with core_database.SessionLocal() as db:
            # Get the IdP configuration
            idp = idp_crud.get_identity_provider(idp_id, db)
            if not idp or not idp.enabled:
                raise core_exceptions.NotFoundError(f"Identity provider (ID: {idp_id}) not found or disabled")

            # Get the encrypted refresh token from database
            encrypted_refresh_token = (
                identity_provider_links_integration.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                    user_id, idp_id, db
                )
            )

        if not encrypted_refresh_token:
            logger.debug(
                "No refresh token stored for user <user_id>, idp <idp_id>. Cannot refresh session.",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None

        # Decrypt the refresh token
        try:
            refresh_token = core_cryptography.decrypt_token_fernet(encrypted_refresh_token)
            if not refresh_token:
                raise ValueError("Decryption returned empty value")
        except Exception as err:
            logger.warning(
                "Failed to decrypt refresh token for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            # Clear corrupted token
            self._clear_refresh_token(user_id, idp_id, encrypted_refresh_token)
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
                self.store_idp_tokens(
                    user_id, idp_id, token_response, db, expected_refresh_token=encrypted_refresh_token
                )
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
                # Clear the rejected token, unless another refresh has replaced it meanwhile
                self._clear_refresh_token(user_id, idp_id, encrypted_refresh_token)
                return None
            logger.warning(
                "IdP refused the session refresh for user <user_id>, idp <idp_id>: <error>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, error=err.error),
            )
            return None

        except Exception as err:
            logger.error(
                "Unexpected error refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            return None
        finally:
            if client is not None:
                client.close()

    @staticmethod
    def _clear_refresh_token(user_id: int, idp_id: int, expected_refresh_token: str) -> None:
        """Clear the refresh token a refresh read, in a session of its own, unless the link holds another now.

        Args:
            user_id: The user whose token to clear.
            idp_id: The provider the token belongs to.
            expected_refresh_token: The encrypted token the refresh read.
        """
        with core_database.SessionLocal() as db:
            cleared = identity_provider_links_integration.clear_user_identity_provider_refresh_token_if_unchanged(
                user_id, idp_id, expected_refresh_token, db
            )
            db.commit()
        if not cleared:
            logger.debug(
                "Kept the IdP refresh token another refresh stored for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return
        logger.info(
            "Cleared the identity-provider refresh token for user <user_id>, idp <idp_id>",
            extra=core_logger.context(user_id=user_id, idp_id=idp_id),
        )
