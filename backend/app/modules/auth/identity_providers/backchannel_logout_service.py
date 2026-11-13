"""OpenID Connect Back-Channel Logout 1.0: end the sessions a provider says the user signed out of."""

import math
import time
import uuid
from typing import Any

import jasil.audit as jasil_audit
from jasil.providers import StateProvider
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.id_token_service as id_token_service
import modules.auth.identity_providers.logout_token_replay_store as logout_token_replay_store
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.utils as identity_provider_utils
import modules.auth.sessions.audit_actions as sessions_audit_actions

logger = core_logger.get_logger(__name__)


class BackchannelLogoutService:
    """Verify a provider's logout token and end the Endurain sessions it names."""

    def __init__(self, oidc: oidc_client_service.OidcClientService, state: StateProvider) -> None:
        """Initialize the service with the client that reaches the providers and the state that records used tokens."""
        self._oidc = oidc
        self._state = state

    def logout(self, idp_slug: str, logout_token: str, db: Session) -> None:
        """Handle a back-channel logout request: verify the logout token, then end the sessions it names.

        The provider is read and the read transaction ended before the discovery document and signing keys are
        fetched, so no database connection is held across those calls; the sessions end in a transaction of their
        own afterwards. A token that names no live session succeeds: the user is already signed out.

        Args:
            idp_slug: The slug of the provider in the request URL.
            logout_token: The ``logout_token`` the provider posted.
            db: Database session.

        Raises:
            NotFoundError: If the provider does not exist or does not identify sign-ins by ID token.
            InvalidInputError: If the token does not verify, is replayed, or the provider's signing keys cannot be
                read; the refusal is audited.
            ServiceUnavailableError: If the state store that records used tokens cannot be reached.

        Any other failure while ending the sessions releases the token's claim and is raised unchanged, so the
        provider's retry of the same token is accepted.
        """
        idp = _require_logout_provider(idp_slug, db)
        db.commit()
        logger.debug("Back-channel logout request for idp <idp_id>", extra=core_logger.context(idp_id=idp.id))
        claims = self._verify(idp, logout_token)
        self._claim_once(idp, claims)
        try:
            _end_sessions(idp.id, claims, db)
        except Exception:
            self._release_claim(idp.id, claims)
            raise

    def _verify(self, idp: identity_provider_contracts.IdentityProviderState, logout_token: str) -> dict[str, Any]:
        """Verify a logout token against the provider's discovered issuer and signing keys.

        Args:
            idp: The provider.
            logout_token: The posted token.

        Returns:
            The verified claims.

        Raises:
            InvalidInputError: If the token does not verify or the issuer and signing keys cannot be read.
        """
        try:
            jwks_uri, issuer = oidc_client_service.require_signing_keys(
                idp, self._oidc.get_oidc_configuration(idp) or {}
            )
            return id_token_service.verify_logout_token(
                self._oidc.fetch_jwks, logout_token, jwks_uri, issuer, self._oidc.decrypt_client_id(idp)
            )
        except core_exceptions.UnauthenticatedError as err:
            raise _refusal(idp.id, idp_audit_actions.BackchannelLogoutRefusal.INVALID_TOKEN) from err
        except (core_exceptions.UpstreamError, oidc_client_service.UpstreamTimeoutError) as err:
            raise _refusal(idp.id, idp_audit_actions.BackchannelLogoutRefusal.SIGNING_KEYS_UNAVAILABLE) from err

    def _claim_once(self, idp: identity_provider_contracts.IdentityProviderState, claims: dict[str, Any]) -> None:
        """Record the token's ``jti`` as used until the token expires, refusing a token already used.

        Args:
            idp: The provider.
            claims: The verified claims.

        Raises:
            InvalidInputError: If the token was already used.
            ServiceUnavailableError: If the state store cannot be reached.
        """
        expires_in = claims["exp"] + id_token_service.ID_TOKEN_CLOCK_LEEWAY_SECONDS - time.time()
        ttl_seconds = max(1, math.ceil(expires_in))
        if not logout_token_replay_store.claim_logout_token(self._state, idp.id, claims["jti"], ttl_seconds):
            raise _refusal(idp.id, idp_audit_actions.BackchannelLogoutRefusal.REPLAYED)

    def _release_claim(self, idp_id: uuid.UUID, claims: dict[str, Any]) -> None:
        """Release the token's claim after the sessions failed to end, so the provider can retry it.

        A release that fails is logged and not raised: the failure that ended the request is what the caller must see.

        Args:
            idp_id: The provider.
            claims: The verified claims.
        """
        try:
            logout_token_replay_store.release_logout_token(self._state, idp_id, claims["jti"])
        except core_exceptions.ServiceUnavailableError as err:
            logger.error(
                "Back-channel logout token for idp <idp_id> could not be released; its retry will be refused",
                extra=core_logger.context(idp_id=idp_id),
                exc_info=err,
            )


def _require_logout_provider(idp_slug: str, db: Session) -> identity_provider_contracts.IdentityProviderState:
    """Return the provider a back-channel logout URL names, if its sign-ins are identified by ID token.

    A provider that issues no ID token has no signing keys a sign-in was verified with and no ``sid`` stored, so
    the endpoint does not exist for it, as for an unknown provider. A disabled provider is still served: a
    logout token naming a sign-in recorded before it was disabled succeeds, as for any session already ended.

    Args:
        idp_slug: The provider slug.
        db: Database session.

    Returns:
        The provider.

    Raises:
        NotFoundError: If the provider does not exist or issues no ID token.
    """
    idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
    if idp is None or not identity_provider_utils.requires_id_token(idp):
        raise core_exceptions.NotFoundError("Identity provider not found or without back-channel logout")
    return idp


def _end_sessions(idp_id: uuid.UUID, claims: dict[str, Any], db: Session) -> None:
    """End the sessions a verified logout token names, audit them per user and commit.

    With a ``sid`` the sessions signed in under that provider session end, only the linked user's when a ``sub``
    is named too; with only a ``sub`` every session the linked user signed in to through the provider ends
    (section 2.7). A ``sub`` no account is linked to names no session.

    Args:
        idp_id: The provider.
        claims: The verified claims, naming a ``sid``, a ``sub`` or both.
        db: Database session.
    """
    sid: str | None = claims.get("sid")
    subject: str | None = claims.get("sub")
    user_id: uuid.UUID | None = None
    if subject is not None:
        link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(idp_id, subject, db)
        if link is None:
            logger.info(
                "Back-channel logout names a subject no account is linked to",
                extra=core_logger.context(idp_id=idp_id),
            )
            return
        user_id = link.user_id
    ended: dict[uuid.UUID, int] = {}
    if sid is not None:
        ended = identity_provider_links_integration.end_idp_sessions_by_sid(idp_id, sid, db, user_id=user_id)
    elif user_id is not None:
        ended[user_id] = identity_provider_links_integration.end_idp_sessions(user_id, idp_id, db)
    for owner_id, count in ended.items():
        if count:
            jasil_audit.stage(
                db,
                sessions_audit_actions.SESSION_REVOKE,
                target_type="user",
                target_id=str(owner_id),
                target_owner_id=str(owner_id),
                details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=count),
            )
    db.commit()
    logger.info(
        "Back-channel logout ended <count> session(s)",
        extra=core_logger.context(count=sum(ended.values()), idp_id=idp_id),
    )


def _refusal(
    idp_id: uuid.UUID, reason: idp_audit_actions.BackchannelLogoutRefusal
) -> core_exceptions.InvalidInputError:
    """Audit a refused back-channel logout and return the 400 the provider is answered with.

    Args:
        idp_id: The provider the request named.
        reason: Why it was refused.

    Returns:
        The error to raise.
    """
    logger.warning(
        "Back-channel logout refused for idp <idp_id>: <reason>",
        extra=core_logger.context(idp_id=idp_id, reason=reason),
    )
    jasil_audit.record_detached(
        idp_audit_actions.BACKCHANNEL_LOGOUT_REFUSE,
        outcome=jasil_audit.Outcome.FAILURE,
        target_type="identity_provider",
        target_id=str(idp_id),
        details=idp_audit_actions.BackchannelLogoutRefusalDetails(idp_id=idp_id, reason=reason),
    )
    return core_exceptions.InvalidInputError("The logout token was refused")
