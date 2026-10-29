"""The start of an SSO login or link flow: authorization URLs and the OAuth state behind them."""

import secrets
from collections.abc import Callable

from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.computation as auth_computation
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.utils as identity_provider_utils
import modules.auth.oauth_state.integration_service as oauth_state_integration

logger = core_logger.get_logger(__name__)


class AuthorizationService:
    """Start an SSO login or account-link flow and hand the browser to the identity provider."""

    def __init__(self, oidc: oidc_client_service.OidcClientService, frontend_host: str) -> None:
        """Initialize the service with the provider client and the host the callback URL is built on."""
        self._oidc = oidc
        self._frontend_host = frontend_host

    def create_login_oauth_state(
        self,
        idp_id: int,
        *,
        client_type: str,
        ip_address: str | None,
        redirect_path: str | None,
        code_challenge: str,
        code_challenge_method: str,
        db: Session,
    ) -> str:
        """Persist the OAuth state of a login flow and return its id.

        Args:
            idp_id: Provider the login goes through.
            client_type: ``web`` or ``mobile``.
            ip_address: Address of the client that started the flow.
            redirect_path: Frontend path to return to after login.
            code_challenge: PKCE challenge the token exchange is checked against.
            code_challenge_method: PKCE method (``S256``).
            db: Database session.

        Returns:
            The state id sent to the provider.
        """
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        oauth_state_integration.create_oauth_state(
            db=db,
            state_id=state_id,
            idp_id=idp_id,
            nonce=nonce,
            client_type=client_type,
            ip_address=ip_address,
            redirect_path=redirect_path,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            idp_code_verifier=_new_code_verifier(),
        )
        db.commit()
        logger.debug(
            "OAuth state created: <state_id> for IdP <idp_id> (client_type=<client_type>)",
            extra=core_logger.context(
                state_id=core_hashing.log_fingerprint(state_id), idp_id=idp_id, client_type=client_type
            ),
        )
        return state_id

    def start_browser_link(
        self,
        link_token: str,
        idp_id: int,
        redirect: str | None,
        client_ip: str | None,
        claim_link_token: Callable[..., int],
        allowed_schemes: set[str],
        db: Session,
    ) -> identity_provider_contracts.BrowserLinkStart:
        """Claim a browser link token, stage OAuth state, and return the provider URL with the browser binding.

        The state stores only a digest of the binding, so the callback can tell the browser that started the
        link from one that was handed its provider URL, and the row alone cannot reproduce the cookie.
        """
        identity_provider_utils.validate_redirect_url(redirect, allowed_schemes)
        user_id = claim_link_token(link_token=link_token, idp_id=idp_id, client_ip=client_ip)
        idp = idp_crud.get_identity_provider(idp_id, db)
        if idp is None or not idp.enabled:
            raise core_exceptions.NotFoundError("Identity provider not found or disabled")
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        client_type = "mobile" if identity_provider_utils.is_custom_scheme_redirect(redirect) else "web"
        browser_binding = secrets.token_urlsafe(32)
        oauth_state_integration.create_oauth_state(
            db=db,
            state_id=state_id,
            idp_id=idp_id,
            nonce=nonce,
            client_type=client_type,
            ip_address=client_ip,
            user_id=user_id,
            redirect_path=redirect,
            browser_binding_hash=core_hashing.sha256_hex(browser_binding),
            idp_code_verifier=_new_code_verifier(),
        )
        authorization_url = self.initiate_link(idp, user_id, db, oauth_state_id=state_id)
        logger.info(
            "User initiated an identity provider link", extra=core_logger.context(user_id=user_id, idp_id=idp_id)
        )
        return identity_provider_contracts.BrowserLinkStart(
            authorization_url=authorization_url, browser_binding=browser_binding
        )

    def initiate_login(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        db: Session,
        redirect_path: str | None = None,
        oauth_state_id: str | None = None,
    ) -> str:
        """Initiates the OAuth2/OIDC login process for the given identity provider.

        This method prepares the authorization URL for the user to authenticate with the specified
        identity provider (IdP). It handles endpoint discovery and authorization URL construction.


        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing
                configuration details.
            request (Request): The current HTTP request object.
            db (Session): The database session.
            redirect_path (str | None): Optional frontend path to redirect to after successful login.
            oauth_state_id (str | None): Database OAuth state ID (from PKCE flow).

        Returns:
            str: The authorization URL to which the user should be redirected to initiate login.

        Raises:
            domain error: If the identity provider is not properly configured or if an error occurs during initiation.
        """
        try:
            client_id = self._oidc.decrypt_client_id(idp)

            # Get endpoints
            authorization_endpoint = idp.authorization_endpoint

            # Try OIDC discovery if issuer URL is provided
            if not authorization_endpoint and idp.issuer_url:
                config = self._oidc.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise core_exceptions.UpstreamError(
                    f"Identity provider {idp.name} authorization "
                    "endpoint could not be resolved. Verify the "
                    "issuer URL is reachable; if it is on a "
                    "private network, add its host or CIDR to "
                    "SSRF_ALLOWED_HOSTS."
                )

            # Retrieve database-backed OAuth state (mandatory for all clients)
            if not oauth_state_id:
                raise core_exceptions.ProcessingError("OAuth state ID is required (PKCE mandatory)")

            oauth_state_obj = oauth_state_integration.get_oauth_state_by_id_and_not_used(oauth_state_id, db)
            if not oauth_state_obj:
                raise core_exceptions.ProcessingError("OAuth state not found")

            state = oauth_state_id
            nonce = oauth_state_obj.nonce

            # Build authorization URL
            redirect_uri = identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug)
            scopes = idp.scopes or "openid profile email"

            with OAuth2Client(
                client_id=client_id, redirect_uri=redirect_uri, scope=scopes, code_challenge_method="S256"
            ) as client:
                authorization_url, _ = client.create_authorization_url(
                    authorization_endpoint, state=state, nonce=nonce, code_verifier=oauth_state_obj.idp_code_verifier
                )

            return authorization_url

        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.debug(
                "Error initiating OAuth login for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to initiate SSO login") from err

    def initiate_link(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        user_id: int,
        db: Session,
        oauth_state_id: str | None = None,
    ) -> str:
        """Initiates the OAuth/OIDC authorization flow for linking an identity provider to an existing user account.

        This method generates the authorization URL that redirects the user to the identity provider's
        login page. Uses database-backed OAuth state for security and replay protection.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider configuration object
                containing client credentials, endpoints, and other OAuth/OIDC settings.
            request (Request): The FastAPI request object used to access and store session data.
            user_id (int): The ID of the authenticated user who is linking their account to the
                identity provider.
            db (Session): The database session for database operations.
            oauth_state_id (str | None): Database OAuth state ID (required for secure linking).

        Returns:
            str: The authorization URL to redirect the user to for identity provider authentication.

        Raises:
            domain error:
                - 500 status code if the identity provider is not properly configured (missing
                  authorization endpoint).
                - 500 status code if OAuth state ID is missing or invalid.
                - 500 status code if any unexpected error occurs during the OAuth flow initiation.

        Note:
            - If authorization_endpoint is not directly configured, the method attempts OIDC
              discovery using the issuer_url.
            - OAuth state is stored in database with user_id to indicate link mode.
        """
        try:
            client_id = self._oidc.decrypt_client_id(idp)

            # Get endpoints
            authorization_endpoint = idp.authorization_endpoint

            # Try OIDC discovery if issuer URL is provided
            if not authorization_endpoint and idp.issuer_url:
                config = self._oidc.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise core_exceptions.UpstreamError(
                    f"Identity provider {idp.name} authorization "
                    "endpoint could not be resolved. Verify the "
                    "issuer URL is reachable; if it is on a "
                    "private network, add its host or CIDR to "
                    "SSRF_ALLOWED_HOSTS."
                )

            # Retrieve database-backed OAuth state (required for link mode)
            if not oauth_state_id:
                raise core_exceptions.ProcessingError("OAuth state ID is required for secure linking")

            oauth_state_obj = oauth_state_integration.get_oauth_state_by_id_and_not_used(oauth_state_id, db)
            if not oauth_state_obj:
                raise core_exceptions.ProcessingError("OAuth state not found")

            # Validate user_id matches (security check for link mode)
            if oauth_state_obj.user_id != user_id:
                raise core_exceptions.ProcessingError("OAuth state user mismatch")

            state = oauth_state_id
            nonce = oauth_state_obj.nonce

            # Build authorization URL
            redirect_uri = identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug)
            scopes = idp.scopes or "openid profile email"

            with OAuth2Client(
                client_id=client_id, redirect_uri=redirect_uri, scope=scopes, code_challenge_method="S256"
            ) as client:
                authorization_url, _ = client.create_authorization_url(
                    authorization_endpoint, state=state, nonce=nonce, code_verifier=oauth_state_obj.idp_code_verifier
                )

            return authorization_url

        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.debug(
                "Error initiating OAuth link for IdP <name>, user <user_id>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, user_id=user_id, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to initiate identity provider linking") from err

    def begin_login(
        self,
        idp_slug: str,
        code_challenge: str,
        code_challenge_method: str,
        redirect: str | None,
        client_ip: str | None,
        header_client_type: str | None,
        allowed_redirect_schemes: set[str],
        db: Session,
    ) -> str:
        """Validate a login request and return the provider's authorization URL.

        PKCE is required of every client (OAuth 2.1). The client type comes from ``X-Client-Type`` unless the
        redirect is a custom scheme, which marks a native app: the browser leg of the flow cannot carry the
        header, so the validated redirect is the authoritative signal.

        Args:
            idp_slug: Slug of the provider to log in through.
            code_challenge: PKCE challenge the token exchange will be checked against.
            code_challenge_method: PKCE method, which must be ``S256``.
            redirect: Frontend path to return to after login.
            client_ip: Address of the client that started the flow.
            header_client_type: The ``X-Client-Type`` header, if any.
            allowed_redirect_schemes: Custom URI schemes a redirect may use.
            db: Database session.

        Returns:
            The authorization URL to send the browser to.

        Raises:
            NotFoundError: If the provider does not exist or is disabled.
            InvalidInputError: If PKCE or the redirect is missing or malformed.
        """
        idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
        if not idp or not idp.enabled:
            raise core_exceptions.NotFoundError("Identity provider not found or disabled")
        if not code_challenge:
            raise core_exceptions.InvalidInputError("code_challenge is required (PKCE mandatory for all clients)")
        if code_challenge_method != "S256":
            raise core_exceptions.InvalidInputError("code_challenge_method must be S256")
        auth_computation.validate_pkce_challenge(code_challenge, code_challenge_method)
        # Refused before anything is stored, so a login cannot be turned into an open redirect.
        identity_provider_utils.validate_redirect_url(redirect, allowed_redirect_schemes)

        if identity_provider_utils.is_custom_scheme_redirect(redirect):
            client_type = "mobile"
        else:
            client_type = header_client_type if header_client_type in ("web", "mobile") else "web"

        state_id = self.create_login_oauth_state(
            idp.id,
            client_type=client_type,
            ip_address=client_ip,
            redirect_path=redirect,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            db=db,
        )
        return self.initiate_login(idp, db, redirect, oauth_state_id=state_id)


def _new_code_verifier() -> str:
    """Return a fresh PKCE verifier for the provider leg of an SSO flow.

    Returns:
        A random 86-character verifier, within the 43 to 128 characters RFC 7636 allows.
    """
    return secrets.token_urlsafe(64)
