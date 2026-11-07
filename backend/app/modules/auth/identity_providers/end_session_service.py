"""RP-initiated logout: end an identity-provider sign-in at the provider when its Endurain session ends."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.oidc_client_service as oidc_client_service

logger = core_logger.get_logger(__name__)


class EndSessionService:
    """Build the provider URL that ends the provider's session (OpenID Connect RP-Initiated Logout 1.0)."""

    def __init__(self, oidc: oidc_client_service.OidcClientService) -> None:
        """Initialize the service with the client that reaches the providers."""
        self._oidc = oidc

    @staticmethod
    def read_end_session(session_id: str, db: Session) -> identity_provider_contracts.EndSessionRequest | None:
        """Read the provider and ID token of the sign-in behind a session, before the session ends.

        Args:
            session_id: The session about to end.
            db: Database session holding the caller's transaction.

        Returns:
            What ending the session at its provider needs, or None when the session did not sign in through a
            provider, the sign-in holds no ID token, or the provider no longer exists.
        """
        sign_in = identity_provider_links_integration.get_idp_session_token(session_id, db)
        if sign_in is None or sign_in.id_token is None:
            return None
        idp = idp_crud.get_identity_provider(sign_in.idp_id, db)
        if idp is None:
            return None
        return identity_provider_contracts.EndSessionRequest(idp=idp, encrypted_id_token=sign_in.id_token)

    def end_session_url(
        self, request: identity_provider_contracts.EndSessionRequest, post_logout_redirect_uri: str | None
    ) -> str | None:
        """Build the provider URL that ends the session at the provider. It may reach the network; hold no database session.

        The user-facing operation, ending the Endurain session, has already succeeded when this runs, so a failure
        here is logged and answers None: the provider session simply stays. The ID token is never logged.

        Args:
            request: The provider and encrypted ID token read before the session ended.
            post_logout_redirect_uri: Where the provider sends the browser afterwards, or None to send it nowhere.

        Returns:
            The provider's end-session endpoint with ``id_token_hint``, ``client_id`` and, when given,
            ``post_logout_redirect_uri`` added to the query it already has; or None when the provider names no
            end-session endpoint or the URL could not be built.
        """
        idp = request.idp
        try:
            endpoint = self._oidc.resolve_end_session_endpoint(idp)
            if endpoint is None:
                return None
            id_token = core_cryptography.decrypt_token_fernet(request.encrypted_id_token)
            client_id = self._oidc.decrypt_client_id(idp)
        except core_exceptions.DomainError as err:
            logger.warning(
                "Could not build the end-session URL for idp <idp_id>; the provider session stays: <err>",
                exc_info=err,
                extra=core_logger.context(idp_id=idp.id, err=err),
            )
            return None
        params = {"id_token_hint": id_token, "client_id": client_id}
        if post_logout_redirect_uri is not None:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri
        parts = urlsplit(endpoint)
        query = urlencode([*parse_qsl(parts.query, keep_blank_values=True), *params.items()])
        return urlunsplit(parts._replace(query=query))
