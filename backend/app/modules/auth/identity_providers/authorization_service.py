"""The start of an SSO login, link or step-up flow: authorization URLs and the OAuth state behind them."""

import secrets
from collections.abc import Callable

from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.computation as auth_computation
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.utils as identity_provider_utils
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration

logger = core_logger.get_logger(__name__)


class AuthorizationService:
    """Start an SSO login, account-link or step-up flow and hand the browser to the identity provider."""

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
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
        )
        db.commit()
        logger.debug(
            "OAuth state created: <state_id> for IdP <idp_id> (client_type=<client_type>)",
            extra=core_logger.context(
                state_id=core_hashing.log_fingerprint(state_id), idp_id=idp_id, client_type=client_type
            ),
        )
        return state_id

    def stage_browser_link(
        self,
        link_token: str,
        idp_id: int,
        redirect: str | None,
        client_ip: str | None,
        claim_link_token: Callable[..., int],
        allowed_schemes: set[str],
        db: Session,
    ) -> identity_provider_contracts.StagedBrowserFlow:
        """Claim a browser link token and stage the link's OAuth state; the caller commits.

        The state stores only a digest of the browser binding, so the callback can tell the browser that started
        the link from one that was handed its provider URL, and the row alone cannot reproduce the cookie.

        Args:
            link_token: One-time token minted for the link.
            idp_id: Provider to link.
            redirect: Frontend path or custom scheme to return to.
            client_ip: Address of the client that started the link.
            claim_link_token: Claims the link token and returns its user.
            allowed_schemes: Custom URI schemes a redirect may use.
            db: Database session.

        Returns:
            The staged flow, for :meth:`authorization_url` once the caller has committed.

        Raises:
            InvalidInputError: If the redirect is not allowed.
            NotFoundError: If the provider does not exist or is disabled.
        """
        identity_provider_utils.validate_redirect_url(redirect, allowed_schemes)
        user_id = claim_link_token(link_token=link_token, idp_id=idp_id, client_ip=client_ip)
        idp = idp_crud.get_identity_provider(idp_id, db)
        if idp is None or not idp.enabled:
            raise core_exceptions.NotFoundError("Identity provider not found or disabled")
        client_type = "mobile" if identity_provider_utils.is_custom_scheme_redirect(redirect) else "web"
        staged = _stage_bound_flow(
            idp,
            oauth_state_constants.OAuthStatePurpose.LINK,
            user_id=user_id,
            client_type=client_type,
            client_ip=client_ip,
            redirect=redirect,
            db=db,
        )
        logger.info(
            "User initiated an identity provider link", extra=core_logger.context(user_id=user_id, idp_id=idp_id)
        )
        return staged

    def stage_step_up(
        self,
        user_id: int,
        session_id: str,
        idp_id: int,
        action: idp_constants.StepUpAction,
        code_challenge: str,
        redirect: str,
        client_ip: str | None,
        db: Session,
    ) -> identity_provider_contracts.StagedBrowserFlow:
        """Stage the OAuth state of a step-up re-authentication; the caller commits.

        Only a provider the user has linked and that publishes signed ID tokens (an issuer for discovery and
        signing keys) can prove a fresh sign-in, so any other is refused here rather than after the round trip.

        Args:
            user_id: The signed-in user.
            session_id: The session the step-up belongs to.
            idp_id: Provider to sign in with again.
            action: The sensitive operation the step-up authorises.
            code_challenge: S256 challenge of the verifier the browser keeps.
            redirect: Frontend path to return to; custom schemes are refused.
            client_ip: Address of the client that started the step-up.
            db: Database session.

        Returns:
            The staged flow, for :meth:`authorization_url` once the caller has committed.

        Raises:
            InvalidInputError: If the redirect or the challenge is malformed, or the provider cannot prove a
                fresh sign-in.
            NotFoundError: If the provider does not exist, is disabled or is not linked to the user.
        """
        # No custom scheme is allowed, and a blank value, which the validator lets through, is no path either.
        identity_provider_utils.validate_redirect_url(redirect, set())
        if not redirect.startswith("/"):
            raise core_exceptions.InvalidInputError("Redirect must be a relative path starting with '/'.")
        auth_computation.validate_pkce_challenge(code_challenge, "S256")
        idp = idp_crud.get_identity_provider(idp_id, db)
        if idp is None or not idp.enabled:
            raise core_exceptions.NotFoundError("Identity provider not found or disabled")
        if not identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
            user_id, idp_id, db
        ):
            raise core_exceptions.NotFoundError("Identity provider is not linked to this account")
        if not idp.issuer_url:
            raise core_exceptions.InvalidInputError(
                f"Identity provider {idp.name} cannot confirm a new sign-in: it has no issuer URL"
            )
        staged = _stage_bound_flow(
            idp,
            oauth_state_constants.OAuthStatePurpose.STEP_UP,
            user_id=user_id,
            client_type="web",
            client_ip=client_ip,
            redirect=redirect,
            db=db,
            session_id=session_id,
            action=action,
            code_challenge=code_challenge,
        )
        logger.info(
            "User <user_id> started a step-up re-authentication with IdP <idp_id> for <action>",
            extra=core_logger.context(user_id=user_id, idp_id=idp_id, action=action),
        )
        return staged

    def authorization_url(self, staged: identity_provider_contracts.StagedBrowserFlow) -> str:
        """Build the provider URL of a staged link or step-up, after its state was committed.

        A step-up asks the provider for a new sign-in (``prompt=login``) no older than the step-up allows
        (``max_age``); the callback enforces the same limit on the ID token's ``auth_time``, so a provider that
        ignores the request is refused rather than trusted.

        Args:
            staged: The committed flow.

        Returns:
            The provider's authorization URL.

        Raises:
            UpstreamError: If the provider's authorization endpoint cannot be resolved.
        """
        extra: dict[str, str] = {}
        if staged.purpose == oauth_state_constants.OAuthStatePurpose.STEP_UP:
            extra = {"prompt": "login", "max_age": str(idp_constants.STEP_UP_MAX_AGE_SECONDS)}
        return self._build_authorization_url(staged.idp, staged.state_id, staged.nonce, staged.idp_code_verifier, extra)

    def _build_authorization_url(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        state: str,
        nonce: str,
        code_verifier: str | None,
        extra: dict[str, str],
    ) -> str:
        """Resolve the provider's authorization endpoint and build the URL the browser is sent to.

        Args:
            idp: The provider.
            state: The OAuth state id.
            nonce: The OIDC nonce.
            code_verifier: The PKCE verifier whose S256 challenge the URL carries.
            extra: Further authorization parameters.

        Returns:
            The authorization URL.

        Raises:
            UpstreamError: If the endpoint is not configured and discovery cannot provide it.
        """
        authorization_endpoint = idp.authorization_endpoint
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
        redirect_uri = identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug)
        scopes = idp.scopes or "openid profile email"
        with OAuth2Client(
            client_id=self._oidc.decrypt_client_id(idp),
            redirect_uri=redirect_uri,
            scope=scopes,
            code_challenge_method="S256",
        ) as client:
            authorization_url, _ = client.create_authorization_url(
                authorization_endpoint, state=state, nonce=nonce, code_verifier=code_verifier, **extra
            )
        return authorization_url

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
            db (Session): The database session.
            redirect_path (str | None): Optional frontend path to redirect to after successful login.
            oauth_state_id (str | None): Database OAuth state ID (from PKCE flow).

        Returns:
            str: The authorization URL to which the user should be redirected to initiate login.

        Raises:
            domain error: If the identity provider is not properly configured or if an error occurs during initiation.
        """
        try:
            # Retrieve database-backed OAuth state (mandatory for all clients)
            if not oauth_state_id:
                raise core_exceptions.ProcessingError("OAuth state ID is required (PKCE mandatory)")

            oauth_state_obj = oauth_state_integration.get_oauth_state_by_id_and_not_used(oauth_state_id, db)
            if not oauth_state_obj:
                raise core_exceptions.ProcessingError("OAuth state not found")

            return self._build_authorization_url(
                idp, oauth_state_id, oauth_state_obj.nonce, oauth_state_obj.idp_code_verifier, {}
            )

        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.debug(
                "Error initiating OAuth login for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to initiate SSO login") from err

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


def _stage_bound_flow(
    idp: identity_provider_contracts.IdentityProviderState,
    purpose: oauth_state_constants.OAuthStatePurpose,
    *,
    user_id: int,
    client_type: str,
    client_ip: str | None,
    redirect: str | None,
    db: Session,
    session_id: str | None = None,
    action: str | None = None,
    code_challenge: str | None = None,
) -> identity_provider_contracts.StagedBrowserFlow:
    """Stage the OAuth state of a flow a signed-in user starts, bound to the browser that starts it.

    Args:
        idp: The provider.
        purpose: ``link`` or ``step_up``.
        user_id: The signed-in user.
        client_type: ``web`` or ``mobile``.
        client_ip: Address of the client that started the flow.
        redirect: Frontend path or custom scheme to return to.
        db: Database session.
        session_id: The session a step-up belongs to.
        action: The operation a step-up authorises.
        code_challenge: S256 challenge of the verifier a step-up's browser keeps.

    Returns:
        The staged flow, with the browser binding the caller sets as a cookie.
    """
    state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
    browser_binding = secrets.token_urlsafe(32)
    idp_code_verifier = _new_code_verifier()
    oauth_state_integration.create_oauth_state(
        db=db,
        state_id=state_id,
        idp_id=idp.id,
        nonce=nonce,
        client_type=client_type,
        ip_address=client_ip,
        user_id=user_id,
        redirect_path=redirect,
        code_challenge=code_challenge,
        code_challenge_method="S256" if code_challenge else None,
        browser_binding_hash=core_hashing.sha256_hex(browser_binding),
        idp_code_verifier=idp_code_verifier,
        purpose=purpose,
        session_id=session_id,
        action=action,
    )
    return identity_provider_contracts.StagedBrowserFlow(
        idp=idp,
        purpose=purpose,
        state_id=state_id,
        nonce=nonce,
        idp_code_verifier=idp_code_verifier,
        browser_binding=browser_binding,
    )


def _new_code_verifier() -> str:
    """Return a fresh PKCE verifier for the provider leg of an SSO flow.

    Returns:
        A random 86-character verifier, within the 43 to 128 characters RFC 7636 allows.
    """
    return secrets.token_urlsafe(64)
