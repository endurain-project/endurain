"""Revocation, at the identity provider, of the refresh tokens of sessions that have ended (RFC 7009)."""

import uuid
from enum import Enum

import httpx2
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.exc import SQLAlchemyError

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.oidc_client_service as oidc_client_service

logger = core_logger.get_logger(__name__)

#: Sign-ins read per window of a pass.
BATCH_SIZE = 100

#: The ``token_type_hint`` of the revocation request: what the stored token is.
_REVOCATION_HINT = "refresh_token"

#: Answers that say the provider could not decide now, so the token is revoked on a later pass; any other
#: answer below 500 refuses the request for good.
_RETRYABLE_STATUS_CODES = frozenset({408, 429})


class _Outcome(Enum):
    """What a revocation attempt decided about a sign-in.

    Attributes:
        DELETE: The sign-in is done and its row can go.
        RETRY: The provider could not be reached or decide; the row stays for a later pass.
    """

    DELETE = "delete"
    RETRY = "retry"


class IdpTokenRevocationService:
    """Revoke the identity-provider refresh token of every session that no longer exists, then forget it."""

    def __init__(self, oidc: oidc_client_service.OidcClientService) -> None:
        """Initialize the service with the client that reaches the providers."""
        self._oidc = oidc

    def revoke_ended_sessions(self, *, user_id: uuid.UUID | None = None) -> int:
        """Revoke and delete the sign-ins whose Endurain session has ended. Blocking; run it on a worker.

        Sign-ins are read in short windows that close before any provider is called. A sign-in is deleted once
        its token was revoked, the provider has no revocation endpoint, the provider refused the request for
        good, or there is no token to revoke. A network error, a 5xx answer or an unreachable discovery document
        keeps the sign-in for a later pass, and the rest of that provider's sign-ins wait for it as well. A
        sign-in whose token another refresh replaced meanwhile is kept.

        Args:
            user_id: Restrict the pass to one user's sign-ins, or None for every user's.

        Returns:
            How many sign-ins were deleted.
        """
        deleted = 0
        unreachable: set[uuid.UUID] = set()
        after_id: uuid.UUID | None = None
        while True:
            with core_database.SessionLocal() as db:
                orphans, last_id = identity_provider_links_integration.get_orphaned_idp_session_tokens_page(
                    after_id, BATCH_SIZE, db, user_id=user_id
                )
            if last_id is None:
                return deleted
            after_id = last_id
            for session_token in orphans:
                if session_token.idp_id in unreachable:
                    continue
                try:
                    outcome = self._revoke(session_token)
                except (core_exceptions.DomainError, SQLAlchemyError) as err:
                    logger.warning(
                        "Could not revoke the identity-provider token of an ended session",
                        exc_info=err,
                        extra=core_logger.context(user_id=session_token.user_id, idp_id=session_token.idp_id),
                    )
                    continue
                if outcome is _Outcome.RETRY:
                    unreachable.add(session_token.idp_id)
                elif outcome is _Outcome.DELETE and self._delete(session_token):
                    deleted += 1

    def _revoke(self, session_token: identity_link_contracts.IdpSessionTokenRead) -> _Outcome:
        """Revoke one sign-in's refresh token at its provider.

        Args:
            session_token: The sign-in of a session that has ended.

        Returns:
            Whether the sign-in is done (``DELETE``) or the revocation must be tried again (``RETRY``).

        Raises:
            domain error: If the encryption key cannot be loaded (``CryptographyError``, which keeps the sign-in)
                or the provider's client credentials cannot be decrypted.
            SQLAlchemyError: If reading the provider fails.
        """
        if session_token.refresh_token is None:
            return _Outcome.DELETE
        try:
            refresh_token = core_cryptography.decrypt_token_fernet(session_token.refresh_token)
        except core_exceptions.UndecryptableError as err:
            logger.warning(
                "The identity-provider token of an ended session for user <user_id> cannot be decrypted, "
                "so it is not revoked",
                exc_info=err,
                extra=core_logger.context(user_id=session_token.user_id),
            )
            return _Outcome.DELETE
        if not refresh_token:
            return _Outcome.DELETE
        with core_database.SessionLocal() as db:
            idp = idp_crud.get_identity_provider(session_token.idp_id, db)
        if idp is None:
            return _Outcome.DELETE
        return self._post_revocation(idp, refresh_token, session_token)

    def _post_revocation(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        refresh_token: str,
        session_token: identity_link_contracts.IdpSessionTokenRead,
    ) -> _Outcome:
        """Send a refresh token to the provider's revocation endpoint.

        The client authenticates as it does at the token endpoint.

        Args:
            idp: The provider that issued the token.
            refresh_token: The decrypted refresh token.
            session_token: The sign-in the token belongs to, for the log.

        Returns:
            ``DELETE`` when the token was revoked, the provider has no revocation endpoint, or the provider
            refused the request for good; ``RETRY`` on a network error, a 5xx or a retryable answer, or when the
            discovery document is unavailable.

        Raises:
            domain error: If the provider's client credentials cannot be decrypted.
        """
        try:
            endpoint = self._oidc.resolve_revocation_endpoint(idp)
        except core_exceptions.UpstreamError as err:
            logger.warning(
                "Could not revoke an identity-provider token: <err>",
                extra=core_logger.context(idp_id=idp.id, err=err),
            )
            return _Outcome.RETRY
        except core_exceptions.InvalidInputError as err:
            logger.warning(
                "The revocation endpoint of identity provider <idp_id> was refused, so its tokens are not revoked: "
                "<detail>",
                extra=core_logger.context(idp_id=idp.id, detail=err.detail),
            )
            return _Outcome.DELETE
        if endpoint is None:
            logger.debug(
                "Identity provider <idp_id> has no revocation endpoint; the token is only forgotten",
                extra=core_logger.context(idp_id=idp.id),
            )
            return _Outcome.DELETE
        client: OAuth2Client | None = None
        try:
            client = self._oidc.create_oauth_client(
                client_id=self._oidc.decrypt_client_id(idp), client_secret=self._oidc.decrypt_client_secret(idp)
            )
            response = client.revoke_token(endpoint, token=refresh_token, token_type_hint=_REVOCATION_HINT)
        except (httpx2.RequestError, httpx2.InvalidURL) as err:
            logger.warning(
                "Network error revoking an identity-provider token for idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(idp_id=idp.id, err=err),
            )
            return _Outcome.RETRY
        finally:
            if client is not None:
                client.close()
        status_code = response.status_code
        if status_code >= 500 or status_code in _RETRYABLE_STATUS_CODES:
            logger.warning(
                "Identity provider <idp_id> could not revoke a token now: <status_code>",
                extra=core_logger.context(idp_id=idp.id, status_code=status_code),
            )
            return _Outcome.RETRY
        if status_code >= 400:
            logger.warning(
                "Identity provider <idp_id> refused to revoke a token: <status_code>",
                extra=core_logger.context(idp_id=idp.id, status_code=status_code),
            )
        else:
            logger.debug(
                "Revoked an identity-provider token at idp <idp_id> for session <session>",
                extra=core_logger.context(
                    idp_id=idp.id, session=core_hashing.log_fingerprint(str(session_token.session_id))
                ),
            )
        return _Outcome.DELETE

    @staticmethod
    def _delete(session_token: identity_link_contracts.IdpSessionTokenRead) -> bool:
        """Delete a sign-in in a session of its own, unless a refresh replaced its token meanwhile.

        Args:
            session_token: The sign-in as it was read.

        Returns:
            True when the row was deleted.
        """
        with core_database.SessionLocal() as db:
            deleted = identity_provider_links_integration.delete_idp_session_token_if_unchanged(
                session_token.session_id, session_token.refresh_token, db
            )
            db.commit()
        if deleted:
            logger.debug(
                "Forgot the identity-provider sign-in of an ended session for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=session_token.user_id, idp_id=session_token.idp_id),
            )
        return deleted
