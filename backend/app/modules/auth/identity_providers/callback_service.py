"""The end of an SSO login, link or step-up flow: the provider's callback, user matching and session creation."""

import hmac
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx2
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import core.timezone as core_timezone
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.id_token_service as id_token_service
import modules.auth.identity_providers.oidc_client_service as oidc_client_service
import modules.auth.identity_providers.step_up_ticket_store as step_up_ticket_store
import modules.auth.identity_providers.token_service as token_service
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.auth.identity_providers.utils as identity_provider_utils
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


class CallbackService:
    """Finish an SSO login, account-link or step-up flow when the identity provider calls back."""

    def __init__(
        self,
        oidc: oidc_client_service.OidcClientService,
        tokens: token_service.IdpTokenService,
        step_up_tickets: step_up_ticket_store.StepUpTicketStore,
        frontend_host: str,
    ) -> None:
        """Initialize the service with the provider client, the token and ticket stores and the frontend host."""
        self._oidc = oidc
        self._tokens = tokens
        self._step_up_tickets = step_up_tickets
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
        self, idp_slug: str, state: str, browser_binding: str | None, db: Session
    ) -> tuple[identity_provider_contracts.IdentityProviderState, oauth_state_schema.OAuthStateRead]:
        """Accept a provider callback: find its provider and claim its one-time state.

        The state is looked up by its opaque id and checked against the provider named in the URL, because
        without that a state minted for one provider could be replayed against another's callback. A link or
        step-up must also finish in the browser that started it: a link's provider URL is otherwise all an
        attacker needs to bind a victim's provider account to their own, and a step-up's to have the victim
        prove a sign-in for the attacker's session. It is then claimed atomically, so of two concurrent
        callbacks with the same state only one continues. A state that is unknown, bound elsewhere, finished
        by another browser or already used gets the same answer, so a caller learns nothing about which of
        those it was.

        Args:
            idp_slug: Slug of the provider from the callback URL.
            state: The ``state`` parameter the provider echoed back.
            browser_binding: The browser's binding cookie, if it sent one.
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
        if oauth_state.purpose != oauth_state_constants.OAuthStatePurpose.LOGIN and not _is_bound_browser(
            browser_binding, oauth_state.browser_binding_hash
        ):
            logger.warning(
                "IdP <purpose> callback refused for state <value_1>: not the browser that started it",
                extra=core_logger.context(
                    purpose=oauth_state.purpose,
                    value_1=core_hashing.log_fingerprint(state),
                    user_id=oauth_state.user_id,
                ),
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
        code: str | None,
        error: str | None,
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
        error. A failed link or step-up returns to the page that started it with an error flag, and a failed
        login to the login page.

        Args:
            idp: The provider the callback came from.
            code: The authorization code, or ``None`` when the provider answered with an error.
            error: The provider's error code, when it sent no code.
            state: The ``state`` parameter, as the provider echoed it.
            oauth_state: The claimed OAuth state.
            ip_address: Client address, recorded on the new session.
            user_agent: Client user agent, recorded on the new session.
            password_hasher: Hasher for the session's refresh token.
            db: Database session.

        Returns:
            The URL to redirect the browser to.
        """
        if code is None:
            logger.warning(
                "IdP <name> answered a <purpose> callback with an error instead of a code: <error>",
                extra=core_logger.context(name=idp.name, purpose=oauth_state.purpose, error=(error or "")[:128]),
            )
            return self._failure_url(oauth_state)
        if oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.STEP_UP:
            return self.complete_step_up_callback(idp, code, oauth_state, db)
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
            return self._failure_url(oauth_state)

    def _failure_url(self, oauth_state: oauth_state_schema.OAuthStateRead) -> str:
        """Return where a failed callback sends the browser: back to where its flow started.

        Args:
            oauth_state: The claimed OAuth state.

        Returns:
            The URL to redirect the browser to.
        """
        if oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.STEP_UP:
            return identity_provider_utils.build_step_up_result_url(
                self._frontend_host, oauth_state.redirect_path, {"step_up_error": "failed"}
            )
        if oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.LINK:
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

            is_link_mode = oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.LINK
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
                idp_event_publishers.publish_idp_linked(link_user_id, idp.id, db)

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

    def complete_step_up_callback(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        code: str,
        oauth_state: oauth_state_schema.OAuthStateRead,
        db: Session,
    ) -> str:
        """Finish a step-up: prove a fresh sign-in of the linked provider account and hand back a ticket.

        Only a signed ID token proves who signed in and when, so userinfo is never consulted. The sign-in must
        be of the provider account linked to the user who started the step-up, and recent enough
        (``auth_time``); nothing else changes: no user is created or updated, no link is made and no provider
        token or session is stored.

        Args:
            idp: The provider the callback came from.
            code: The authorization code.
            oauth_state: The claimed step-up state.
            db: Database session.

        Returns:
            The page that started the step-up, with ``step_up_ticket`` or ``step_up_error`` in the fragment.
        """
        try:
            subject = self._verify_step_up_sign_in(idp, code, oauth_state)
            link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(
                idp.id, subject, db
            )
            if link is None or link.user_id != oauth_state.user_id:
                logger.warning(
                    "Step-up refused for user <user_id>: IdP <name> signed in an account not linked to them",
                    extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name),
                )
                return self._failure_url(oauth_state)
            ticket = self._step_up_tickets.issue(
                identity_provider_contracts.StepUpTicket(
                    user_id=link.user_id,
                    session_id=oauth_state.session_id,
                    idp_id=idp.id,
                    code_challenge=oauth_state.code_challenge,
                    action=oauth_state.action,
                )
            )
        except _StaleSignInError as err:
            logger.warning(
                "Step-up refused for user <user_id>: IdP <name> did not prove a fresh sign-in (<reason>)",
                extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name, reason=str(err)),
            )
            return identity_provider_utils.build_step_up_result_url(
                self._frontend_host, oauth_state.redirect_path, {"step_up_error": "not_fresh"}
            )
        except Exception as err:
            logger.warning(
                "Step-up re-authentication with IdP <name> failed for user <user_id>",
                exc_info=err,
                extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name),
            )
            return self._failure_url(oauth_state)
        logger.info(
            "User <user_id> re-authenticated with IdP <name> for <action>",
            extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name, action=oauth_state.action),
        )
        return identity_provider_utils.build_step_up_result_url(
            self._frontend_host, oauth_state.redirect_path, {"step_up_ticket": ticket}
        )

    def _verify_step_up_sign_in(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        code: str,
        oauth_state: oauth_state_schema.OAuthStateRead,
    ) -> str:
        """Redeem the code and return the subject of a verified, fresh ID token.

        Args:
            idp: The provider.
            code: The authorization code.
            oauth_state: The claimed step-up state.

        Returns:
            The ``sub`` claim of the verified ID token.

        Raises:
            UpstreamError: If the provider publishes no issuer or signing keys, or returns no ID token.
            UnauthenticatedError: If the ID token does not verify or names no subject.
            _StaleSignInError: If the ID token does not prove a sign-in within the step-up's limit.
        """
        client_id = self._oidc.decrypt_client_id(idp)
        config = self._oidc.get_oidc_configuration(idp) or {}
        jwks_uri = config.get("jwks_uri")
        issuer = config.get("issuer")
        if not jwks_uri or not issuer:
            logger.warning(
                "Step-up refused: IdP <name> publishes no issuer or signing keys",
                extra=core_logger.context(name=idp.name),
            )
            raise core_exceptions.UpstreamError(f"Identity provider {idp.name} publishes no issuer or signing keys")
        with self._oidc.create_oauth_client(
            client_id=client_id,
            client_secret=self._oidc.decrypt_client_secret(idp),
            redirect_uri=identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug),
        ) as oauth_client:
            token_response = oauth_client.fetch_token(
                self._oidc.resolve_token_endpoint(idp),
                grant_type="authorization_code",
                code=code,
                code_verifier=oauth_state.idp_code_verifier,
            )
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str):
            logger.warning("Step-up refused: IdP <name> returned no ID token", extra=core_logger.context(name=idp.name))
            raise core_exceptions.UpstreamError(f"Identity provider {idp.name} returned no ID token")
        claims = id_token_service.verify_id_token(
            self._oidc.fetch_jwks, id_token, jwks_uri, issuer, client_id, expected_nonce=oauth_state.nonce
        )
        _require_fresh_sign_in(claims, oauth_state)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            logger.warning(
                "Step-up refused: IdP <name> issued an ID token with no subject",
                extra=core_logger.context(name=idp.name),
            )
            raise core_exceptions.UnauthenticatedError("ID token names no subject")
        return subject

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


class _StaleSignInError(Exception):
    """The provider's ID token does not prove a sign-in recent enough for a step-up."""


def _require_fresh_sign_in(claims: dict[str, Any], oauth_state: oauth_state_schema.OAuthStateRead) -> None:
    """Require the ID token's ``auth_time`` to fall after the step-up started.

    A provider that reused its own session instead of signing the user in again reports the earlier sign-in, so
    this check, not the ``prompt=login`` the request asked for, is what makes the step-up fresh. The start is
    derived from the state's expiry, which this server set, so the database clock plays no part.

    Args:
        claims: The verified ID-token claims.
        oauth_state: The claimed step-up state.

    Raises:
        _StaleSignInError: If ``auth_time`` is missing, malformed, before the step-up started or in the future,
            each beyond the step-up's tolerance.
    """
    auth_time = claims.get("auth_time")
    if isinstance(auth_time, bool) or not isinstance(auth_time, int | float):
        raise _StaleSignInError("no auth_time claim")
    expires_at = core_timezone.to_utc_aware(oauth_state.expires_at)
    started = expires_at - timedelta(seconds=oauth_state_constants.STATE_TTL_SECONDS)
    tolerance = idp_constants.STEP_UP_MAX_AGE_SECONDS
    if auth_time < started.timestamp() - tolerance:
        raise _StaleSignInError("sign-in predates the step-up")
    if auth_time > datetime.now(UTC).timestamp() + tolerance:
        raise _StaleSignInError("sign-in is in the future")


def _is_bound_browser(browser_binding: str | None, binding_hash: str | None) -> bool:
    """Tell whether a callback comes from the browser that started the link or step-up.

    Args:
        browser_binding: The browser's link-binding cookie, if it sent one.
        binding_hash: The digest the link's OAuth state stored, if any.

    Returns:
        True when both are present and the cookie hashes to the stored digest.
    """
    if not browser_binding or not binding_hash:
        return False
    return hmac.compare_digest(core_hashing.sha256_hex(browser_binding), binding_hash)
