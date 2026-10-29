"""The end of an SSO login or link flow: the provider's callback, user matching and session creation."""

import hmac
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx2
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.token_service as token_service
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.auth.identity_providers.utils as identity_provider_utils
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


class CallbackService:
    """Finish an SSO login or account-link flow when the identity provider calls back."""

    def __init__(
        self,
        oidc: oidc_client_service.OidcClientService,
        tokens: token_service.IdpTokenService,
        frontend_host: str,
    ) -> None:
        """Initialize the service with the provider client, the token store and the frontend host."""
        self._oidc = oidc
        self._tokens = tokens
        self._frontend_host = frontend_host

    def get_unused_oauth_state(self, state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
        """Return an OAuth state that is unexpired and not yet consumed.

        Args:
            state_id: State returned by the provider.
            db: Database session.

        Returns:
            The state, or ``None`` if it is unknown, expired or used.
        """
        return oauth_state_integration.get_oauth_state_by_id_and_not_used(state_id, db)

    def claim_oauth_state(self, state_id: str, db: Session) -> bool:
        """Consume an OAuth state exactly once and commit the claim.

        The claim is committed at once so a callback that fails later cannot be replayed with the same state.

        Args:
            state_id: State returned by the provider.
            db: Database session.

        Returns:
            True if this call consumed the state, False if another callback already had.
        """
        claimed = oauth_state_integration.mark_oauth_state_used(state_id, db)
        db.commit()
        logger.debug(
            "OAuth state claim committed: <state_id> (claimed=<claimed>)",
            extra=core_logger.context(state_id=core_hashing.log_fingerprint(state_id), claimed=claimed),
        )
        return claimed

    def prepare_callback(
        self, idp_slug: str, state: str, link_binding: str | None, db: Session
    ) -> tuple[identity_provider_contracts.IdentityProviderState, oauth_state_schema.OAuthStateRead]:
        """Accept a provider callback: find its provider and claim its one-time state.

        The state is looked up by its opaque id and checked against the provider named in the URL, because
        without that a state minted for one provider could be replayed against another's callback. A link
        must also finish in the browser that started it: its provider URL is otherwise all an attacker needs
        to bind a victim's provider account to their own. It is then claimed atomically, so of two concurrent
        callbacks with the same state only one continues. A state that is unknown, bound elsewhere, finished
        by another browser or already used gets the same answer, so a caller learns nothing about which of
        those it was.

        Args:
            idp_slug: Slug of the provider from the callback URL.
            state: The ``state`` parameter the provider echoed back.
            link_binding: The browser's link-binding cookie, if it sent one.
            db: Database session.

        Returns:
            The provider and the claimed OAuth state.

        Raises:
            NotFoundError: If the provider does not exist or is disabled.
            InvalidInputError: If the state is unknown, expired, bound to another provider or already used.
        """
        idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
        if not idp or not idp.enabled:
            raise core_exceptions.NotFoundError("Identity provider not found or disabled")

        oauth_state = self.get_unused_oauth_state(state, db)
        if not oauth_state:
            logger.warning(
                "OAuth state not found in database: <value_1>",
                extra=core_logger.context(value_1=core_hashing.log_fingerprint(state)),
            )
            raise core_exceptions.InvalidInputError("Invalid or expired OAuth state")
        if oauth_state.idp_id is not None and oauth_state.idp_id != idp.id:
            logger.warning(
                "OAuth state IdP mismatch for state <value_1>: state.idp_id=<idp_id>, callback idp.id=<id>",
                extra=core_logger.context(
                    value_1=core_hashing.log_fingerprint(state), idp_id=oauth_state.idp_id, id=idp.id
                ),
            )
            raise core_exceptions.InvalidInputError("Invalid or expired OAuth state")
        if oauth_state.user_id is not None and not _is_bound_browser(link_binding, oauth_state.browser_binding_hash):
            logger.warning(
                "IdP link callback refused for state <value_1>: not the browser that started the link",
                extra=core_logger.context(value_1=core_hashing.log_fingerprint(state), user_id=oauth_state.user_id),
            )
            raise core_exceptions.InvalidInputError("Invalid or expired OAuth state")
        if not self.claim_oauth_state(state, db):
            logger.warning(
                "OAuth state replay/race rejected: <value_1>",
                extra=core_logger.context(value_1=core_hashing.log_fingerprint(state)),
            )
            raise core_exceptions.InvalidInputError("Invalid or expired OAuth state")

        logger.debug(
            "OAuth callback received for state <value_1> (client_type=<client_type>)",
            extra=core_logger.context(value_1=core_hashing.log_fingerprint(state), client_type=oauth_state.client_type),
        )
        return idp, oauth_state

    def complete_callback(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        code: str,
        state: str,
        oauth_state: oauth_state_schema.OAuthStateRead,
        ip_address: str,
        user_agent: str,
        password_hasher: credentials_integration.PasswordHasher,
        db: Session,
    ) -> str:
        """Finish a callback and return where to send the browser, whatever happened.

        This is the browser leg of the flow, so it always ends in a redirect: a failure after the state was
        claimed (the provider refused the code, a user could not be created) must not leave the user on a JSON
        error. A failed link returns to the page that started it with an error flag, and a failed login to the
        login page.

        Args:
            idp: The provider the callback came from.
            code: The authorization code.
            state: The ``state`` parameter, as the provider echoed it.
            oauth_state: The claimed OAuth state.
            ip_address: Client address, recorded on the new session.
            user_agent: Client user agent, recorded on the new session.
            password_hasher: Hasher for the session's refresh token.
            db: Database session.

        Returns:
            The URL to redirect the browser to.
        """
        try:
            result = self.handle_callback(idp, code, state, password_hasher, oauth_state, db)
            user = result["user"]

            if result.get("mode") == "link":
                logger.info(
                    "IdP link successful for user <username_log_id>, IdP <name>",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
                    ),
                )
                return identity_provider_utils.build_link_result_url(
                    self._frontend_host, oauth_state.redirect_path, idp.name, success=True
                )

            # Login: a session without tokens, which the token exchange completes after PKCE.
            session_id = self.create_callback_session(user, ip_address, user_agent, password_hasher, oauth_state.id, db)
            redirect_url = f"{self._frontend_host}/login?sso=success&session_id={session_id}"
            redirect_path = result.get("redirect_path")
            if redirect_path:
                # Encoded so a "&" or "#" in the path cannot start another query parameter; "/" and ":" stay
                # readable and the frontend decodes the value back.
                redirect_url += f"&redirect={quote(redirect_path, safe='/:')}"
                # A custom scheme tells the frontend to skip its own token exchange and pass the session id on
                # to the native app.
                if "://" in redirect_path and not redirect_path.startswith("http"):
                    redirect_url += "&external_redirect=true"

            # The session id is the handle exchanged for tokens, so only a one-way fingerprint is logged.
            logger.info(
                "SSO login successful for user <username_log_id> via <name> (session=<value_3>)",
                extra=core_logger.context(
                    username_log_id=lockout_integration.username_log_identifier(user.username),
                    name=idp.name,
                    value_3=core_hashing.log_fingerprint(session_id),
                ),
            )
            return redirect_url
        except user_provisioning_service.SsoSignInRefusedError as err:
            # A provider's configuration the login page explains, not a failure of this server.
            logger.warning(
                "SSO sign-in refused for IdP <name>: <detail>",
                extra=core_logger.context(name=idp.name, detail=err.detail),
            )
            return f"{self._frontend_host}/login?error={err.login_error}"
        except Exception as err:
            logger.error("Error in SSO callback: <err>", exc_info=err, extra=core_logger.context(err=err))
            # A link attempt is the one whose OAuth state carries the user who started it.
            if oauth_state.user_id is not None:
                return identity_provider_utils.build_link_result_url(
                    self._frontend_host, oauth_state.redirect_path, None, success=False
                )
            return f"{self._frontend_host}/login?error=sso_failed"

    def handle_callback(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        code: str,
        state: str,
        password_hasher: credentials_integration.PasswordHasher,
        oauth_state: oauth_state_schema.OAuthStateRead,
        db: Session,
    ) -> dict[str, Any]:
        """Handle the OAuth2/OIDC callback from an identity provider.

        This method processes the authorization code received from an identity provider,
        validates the state parameter, exchanges the code for tokens, retrieves user
        information, and either creates/updates a user session (login mode) or links
        the identity provider to an existing user account (link mode).

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider configuration object.
            code (str): The authorization code returned by the identity provider.
            state (str): The state parameter for CSRF protection (database state ID).
            request (Request): The FastAPI/Starlette request object.
            password_hasher (credentials_integration.PasswordHasher): Password hasher instance
                for user authentication operations.
            db (Session): SQLAlchemy database session.
            oauth_state (oauth_state_schema.OAuthStateRead): OAuth-state data.

        Returns:
            dict[str, Any]: A dictionary containing:
                - user: The authenticated or linked user object
                - token_data: OAuth2 token response (access_token, refresh_token, etc.)
                - userinfo: User information claims from the identity provider
                - mode (optional): "link" if this was a link operation (not present for login)

        Raises:
            domain error: With appropriate status codes for various error conditions:
                - 400 BAD_REQUEST: Invalid/expired state, missing parameters, user ID mismatch
                - 404 NOT_FOUND: User not found during link mode
                - 409 CONFLICT: IdP account already linked to a user
                - 500 INTERNAL_SERVER_ERROR: Unexpected errors during authentication
                - 502 BAD_GATEWAY: IdP communication errors, invalid responses
                - 504 GATEWAY_TIMEOUT: IdP not responding

        Notes:
            - State parameter must be valid and not older than 10 minutes (CSRF protection)
            - In link mode, validates that the IdP account is not already linked to any user
            - In login mode, creates new user accounts if they don't exist (SSO provisioning)
            - Stores IdP tokens securely for future session renewal
            - Performs ID token verification if JWKS URI is available
            - Cleans up OAuth state from database after successful completion
        """
        oauth_client: OAuth2Client | None = None
        try:
            # Use database-backed OAuth state (mandatory for all clients)
            redirect_path = oauth_state.redirect_path
            client_type = oauth_state.client_type

            logger.debug(
                "Using database OAuth state for IdP <name> (client_type=<client_type>)",
                extra=core_logger.context(name=idp.name, client_type=client_type),
            )

            # Detect link mode from OAuth state (user_id indicates authenticated user linking)
            is_link_mode = oauth_state.user_id is not None
            link_user_id = oauth_state.user_id

            if is_link_mode:
                # Link mode: OAuth state was created during authenticated linking request
                # The user_id in oauth_state proves the user initiated this link
                logger.debug(
                    "Link mode detected for IdP <name>, user_id=<link_user_id>",
                    extra=core_logger.context(name=idp.name, link_user_id=link_user_id),
                )

            # Decrypt credentials and resolve endpoints using helper methods
            client_id = self._oidc.decrypt_client_id(idp)
            client_secret = self._oidc.decrypt_client_secret(idp)
            token_endpoint = self._oidc.resolve_token_endpoint(idp)

            # Get OIDC configuration (for userinfo, jwks_uri, issuer)
            userinfo_endpoint = idp.userinfo_endpoint
            jwks_uri = None
            expected_issuer = None

            if idp.issuer_url:
                try:
                    config = self._oidc.get_oidc_configuration(idp)
                    if config:
                        # Get userinfo endpoint if not manually configured
                        if not userinfo_endpoint:
                            userinfo_endpoint = config.get("userinfo_endpoint")

                        # Get JWKS URI for ID token verification
                        jwks_uri = config.get("jwks_uri")
                        expected_issuer = config.get("issuer")

                        logger.debug(
                            "OIDC discovery complete for <name>: userinfo=<value_2>, jwks_uri=<value_3>, "
                            "issuer=<value_4>",
                            extra=core_logger.context(
                                name=idp.name,
                                value_2=bool(userinfo_endpoint),
                                value_3=bool(jwks_uri),
                                value_4=bool(expected_issuer),
                            ),
                        )
                except Exception as err:
                    logger.warning(
                        "OIDC discovery failed for IdP <name>: <err>",
                        exc_info=err,
                        extra=core_logger.context(name=idp.name, err=err),
                    )

            # Retrieve nonce from database state
            expected_nonce = oauth_state.nonce

            # Exchange code for tokens
            redirect_uri = identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug)

            try:
                oauth_client = self._oidc.create_oauth_client(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                )

                token_response = oauth_client.fetch_token(
                    token_endpoint,
                    grant_type="authorization_code",
                    code=code,
                    code_verifier=oauth_state.idp_code_verifier,
                )
            except httpx2.TimeoutException as err:
                logger.warning(
                    "Timeout connecting to IdP <name> token endpoint: <err>",
                    extra=core_logger.context(name=idp.name, err=err),
                )
                raise oidc_client_service.UpstreamTimeoutError(
                    f"Identity provider {idp.name} is not responding. Please try again later."
                ) from err
            except httpx2.HTTPStatusError as err:
                logger.warning(
                    "HTTP error from IdP <name> token endpoint: <status_code>",
                    extra=core_logger.context(name=idp.name, status_code=err.response.status_code),
                )
                # Check for common OAuth2 error responses
                if err.response.status_code == 400:
                    detail = "Authorization code is invalid or expired. Please try logging in again."
                elif err.response.status_code == 401:
                    detail = (
                        f"Identity provider {idp.name} rejected the authentication request. "
                        "Please contact administrator."
                    )
                else:
                    detail = f"Identity provider {idp.name} returned an error. Please try again later."

                raise core_exceptions.UpstreamError(detail) from err
            except httpx2.RequestError as err:
                logger.warning(
                    "Network error connecting to IdP <name>: <err>",
                    extra=core_logger.context(name=idp.name, err=err),
                )
                raise core_exceptions.UpstreamError(
                    f"Unable to connect to identity provider {idp.name}. Please check your network connection."
                ) from err
            except Exception as err:
                logger.debug(
                    "Unexpected error during token exchange with IdP <name>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, err=err),
                )
                raise core_exceptions.ProcessingError("Failed to complete authentication. Please try again.") from err

            # Get user information with ID token verification
            userinfo = self._oidc.get_userinfo(
                token_response=token_response,
                userinfo_endpoint=userinfo_endpoint,
                client=oauth_client,
                jwks_uri=jwks_uri,
                expected_issuer=expected_issuer,
                expected_audience=client_id,
                expected_nonce=expected_nonce,
            )

            # Extract subject (unique user identifier)
            subject = userinfo.get("sub") or userinfo.get("id")
            if not subject:
                logger.debug(
                    "IdP <name> did not provide 'sub' or 'id' claim in userinfo: <value_2>",
                    extra=core_logger.context(name=idp.name, value_2=list(userinfo.keys())),
                )
                raise core_exceptions.UpstreamError(
                    f"Identity provider {idp.name} did not provide required user identifier. "
                    "Please contact administrator."
                )

            # Handle link mode differently from login mode
            if is_link_mode and link_user_id:
                # LINK MODE: Associate IdP with existing authenticated user

                # Verify user exists
                user = users_integration.get_user(link_user_id, db)
                if not user:
                    raise core_exceptions.NotFoundError("User not found")

                # Check if this IdP subject is already linked to ANY user
                existing_link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(
                    idp.id, subject, db
                )
                if existing_link:
                    # Check if it's already linked to THIS user
                    if existing_link.user_id == link_user_id:
                        raise core_exceptions.ConflictError(
                            f"This {idp.name} account is already linked to your account"
                        )
                    else:
                        # Linked to a DIFFERENT user - security issue
                        raise core_exceptions.ConflictError(
                            f"This {idp.name} account is already linked to another user"
                        )

                # Create the link
                identity_provider_links_integration.create_user_identity_provider(
                    user_id=link_user_id, idp_id=idp.id, idp_subject=subject, db=db
                )

                # Update user info if sync is enabled
                if idp.sync_user_info:
                    user = user_provisioning_service.update_user_from_idp(user, idp, userinfo, db)

                # Store IdP tokens for future use
                self._tokens.store_idp_tokens(link_user_id, idp.id, token_response, db)

                logger.info(
                    "User <username_log_id> (id=<link_user_id>) linked IdP <name> (subject=<subject>)",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(user.username),
                        link_user_id=link_user_id,
                        name=idp.name,
                        subject=subject,
                    ),
                )

                db.commit()

                # Return special structure for link mode (no new session created)
                return {
                    "user": user,
                    "token_data": token_response,
                    "userinfo": userinfo,
                    "mode": "link",  # Indicate this was a link operation
                }
            else:
                # LOGIN MODE: Find or create user and establish session
                user = user_provisioning_service.find_or_create_user(idp, subject, userinfo, password_hasher, db)

                # Store IdP tokens for future session renewal
                self._tokens.store_idp_tokens(user.id, idp.id, token_response, db)

                db.commit()
                logger.info(
                    "User <username_log_id> authenticated via IdP <name>",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
                    ),
                )

                return {
                    "user": user,
                    "token_data": token_response,
                    "userinfo": userinfo,
                    "redirect_path": redirect_path,
                    "client_type": client_type,
                }

        except core_exceptions.DomainError:
            # Re-raise domain errors as-is (already have proper status codes and messages)
            raise
        except Exception as err:
            # Catch-all for unexpected errors
            logger.debug(
                "Unexpected error handling OAuth callback for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError(
                f"An unexpected error occurred during authentication with {idp.name}. "
                "Please try again or contact administrator."
            ) from err
        finally:
            if oauth_client is not None:
                oauth_client.close()

    def create_callback_session(
        self,
        user: Any,
        ip_address: str,
        user_agent: str,
        password_hasher: credentials_integration.PasswordHasher,
        oauth_state_id: str,
        db: Session,
    ) -> str:
        """Create the token-exchange session for a successful SSO login."""
        users_integration.require_active_user(user)
        user_read = users_schema.UsersRead.model_validate(user)
        session_id = str(uuid4())
        expires_at = datetime.now(UTC) + server_settings_integration.get_session_policy(db).refresh_token_ttl
        sessions_integration.create_session(
            session_id,
            user_read,
            ip_address,
            user_agent,
            None,
            password_hasher,
            expires_at,
            db,
            oauth_state_id=oauth_state_id,
        )
        db.commit()
        logger.debug("SSO callback session created", extra=core_logger.context(user_id=user_read.id))
        return session_id


def _is_bound_browser(link_binding: str | None, binding_hash: str | None) -> bool:
    """Tell whether a callback comes from the browser that started the link.

    Args:
        link_binding: The browser's link-binding cookie, if it sent one.
        binding_hash: The digest the link's OAuth state stored, if any.

    Returns:
        True when both are present and the cookie hashes to the stored digest.
    """
    if not link_binding or not binding_hash:
        return False
    return hmac.compare_digest(core_hashing.sha256_hex(link_binding), binding_hash)
