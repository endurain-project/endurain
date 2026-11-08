"""The end of an SSO login, link or step-up flow: the provider's callback, user matching and session creation."""

import hmac
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

import httpx2
import jasil.audit as jasil_audit
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import OAuth2Client
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import core.timezone as core_timezone
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.audit_actions as idp_audit_actions
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
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.login_audit.integration_service as login_audit_integration
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.sessions.audit_actions as sessions_audit_actions
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


@dataclass(frozen=True)
class CallbackResult:
    """The outcome of a sign-in or link callback.

    Attributes:
        user: The user who signed in, or whose account the provider was linked to.
        userinfo: The claims the provider returned for the user.
        mode: Whether the callback signed the user in or linked the provider.
        redirect_path: Where the frontend sends the user after a sign-in, when the flow named one.
        token_response: The provider's token response of a sign-in, kept for the session it creates; empty for a
            link, which creates no session. It holds secrets, so it is left out of the representation.
    """

    user: users_schema.UserRead
    userinfo: dict[str, Any]
    mode: Literal["login", "link"]
    redirect_path: str | None = None
    token_response: dict[str, Any] = field(default_factory=dict, repr=False)


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
            _record_state_refusal(idp.id, None)
            raise core_exceptions.InvalidInputError("Invalid or expired OAuth state")
        if oauth_state.idp_id is not None and oauth_state.idp_id != idp.id:
            logger.warning(
                "OAuth state IdP mismatch for state <value_1>: state.idp_id=<idp_id>, callback idp.id=<id>",
                extra=core_logger.context(
                    value_1=core_hashing.log_fingerprint(state), idp_id=oauth_state.idp_id, id=idp.id
                ),
            )
            _record_state_refusal(idp.id, oauth_state)
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
            _record_browser_mismatch(idp.id, oauth_state)
            raise core_exceptions.InvalidInputError("Invalid or expired OAuth state")
        if not self.claim_oauth_state(state, db):
            logger.warning(
                "OAuth state replay/race rejected: <value_1>",
                extra=core_logger.context(value_1=core_hashing.log_fingerprint(state)),
            )
            _record_state_refusal(idp.id, oauth_state)
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
            _record_provider_refusal(idp.id, oauth_state, _PROVIDER_ERROR)
            return self._failure_url(oauth_state)
        if oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.STEP_UP:
            step_up_state = oauth_state_schema.StepUpOAuthStateRead.model_validate(oauth_state, from_attributes=True)
            return self.complete_step_up_callback(idp, code, step_up_state, db)
        try:
            result = self.handle_callback(idp, code, state, oauth_state, db)
            user = result.user

            if result.mode == "link":
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
            session_id = self.create_callback_session(
                user,
                ip_address,
                user_agent,
                password_hasher,
                oauth_state,
                idp.id,
                result.token_response,
                db,
                idp_sid=_provider_session_id(result.userinfo),
            )
            redirect_url = f"{self._frontend_host}/login?sso=success&session_id={session_id}"
            redirect_path = result.redirect_path
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
        except core_exceptions.ProcessingError as err:
            logger.error("Error in SSO callback: <err>", exc_info=err, extra=core_logger.context(err=err))
            return self._failure_url(oauth_state)
        except core_exceptions.DomainError as err:
            # The provider failed or refused, or the account cannot be linked: an expected outcome, not a bug.
            logger.warning(
                "SSO callback for IdP <name> refused: <err>",
                extra=core_logger.context(name=idp.name, err=err),
            )
            return self._failure_url(oauth_state)
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
        oauth_state: oauth_state_schema.OAuthStateRead,
        db: Session,
    ) -> CallbackResult:
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
            db (Session): SQLAlchemy database session.
            oauth_state (oauth_state_schema.OAuthStateRead): OAuth-state data.

        Returns:
            CallbackResult: The user, the provider's claims, whether the callback signed in or linked, and the
                sign-in's redirect path.

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
            - In login mode, returns the provider's tokens so the session that signs the user in stores them
            - A provider that issues an ID token (OIDC, or OAuth 2.0 with the openid scope) must return one that
              verifies against the discovered issuer and signing keys, with the nonce of the authorization request
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
            require_id_token = identity_provider_utils.requires_id_token(idp)

            if require_id_token:
                # A login identified by a verified ID token needs discovery to succeed.
                config = self._oidc.get_oidc_configuration(idp) or {}
                jwks_uri, expected_issuer = oidc_client_service.require_signing_keys(idp, config)
                userinfo_endpoint = userinfo_endpoint or config.get("userinfo_endpoint")
            elif idp.issuer_url:
                # Discovery logs its own failure and returns None; the provider then goes on without it
                discovered = self._oidc.get_oidc_configuration(idp)
                if discovered:
                    # Get userinfo endpoint if not manually configured
                    if not userinfo_endpoint:
                        userinfo_endpoint = discovered.get("userinfo_endpoint")

                    # Get JWKS URI for ID token verification
                    jwks_uri = discovered.get("jwks_uri")
                    expected_issuer = discovered.get("issuer")

            logger.debug(
                "OIDC discovery complete for <name>: userinfo=<value_2>, jwks_uri=<value_3>, issuer=<value_4>",
                extra=core_logger.context(
                    name=idp.name,
                    value_2=bool(userinfo_endpoint),
                    value_3=bool(jwks_uri),
                    value_4=bool(expected_issuer),
                ),
            )

            # Retrieve nonce from database state
            expected_nonce = oauth_state.nonce

            # Exchange code for tokens
            redirect_uri = identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug)

            oauth_client = self._oidc.create_oauth_client(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
            try:
                token_response = self._exchange_code(
                    idp, oauth_client, token_endpoint, code, oauth_state.idp_code_verifier
                )
            except core_exceptions.DomainError:
                _record_provider_refusal(idp.id, oauth_state, _TOKEN_EXCHANGE_FAILED)
                raise

            # Get user information with ID token verification
            try:
                userinfo = self._oidc.get_userinfo(
                    token_response=token_response,
                    userinfo_endpoint=userinfo_endpoint,
                    client=oauth_client,
                    jwks_uri=jwks_uri,
                    expected_issuer=expected_issuer,
                    expected_audience=client_id,
                    expected_nonce=expected_nonce,
                    require_id_token=require_id_token,
                )
            except core_exceptions.UnauthenticatedError:
                if not is_link_mode:
                    _record_login_refusal(
                        jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.INVALID_ID_TOKEN
                    )
                raise

            # Extract subject (unique user identifier)
            subject = userinfo.get("sub") or userinfo.get("id")
            if not subject:
                _record_provider_refusal(idp.id, oauth_state, _NO_SUBJECT)
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
                    user_provisioning_service.record_identity_link_refused(
                        link_user_id,
                        idp.id,
                        idp_audit_actions.IdentityLinkRefusal.USER_NOT_FOUND,
                        jasil_audit.Outcome.FAILURE,
                    )
                    raise core_exceptions.NotFoundError("User not found")

                # The browser binding proved the user started this link, so the rows below name them as actor.
                with login_audit_integration.acting_as_user(link_user_id):
                    # Check if this IdP subject is already linked to ANY user
                    existing_link = (
                        identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(
                            idp.id, subject, db
                        )
                    )
                    if existing_link:
                        # Check if it's already linked to THIS user
                        if existing_link.user_id == link_user_id:
                            user_provisioning_service.record_identity_link_refused(
                                link_user_id,
                                idp.id,
                                idp_audit_actions.IdentityLinkRefusal.ALREADY_LINKED_TO_THIS_ACCOUNT,
                            )
                            raise core_exceptions.ConflictError(
                                f"This {idp.name} account is already linked to your account"
                            )
                        else:
                            # Linked to a DIFFERENT user - security issue
                            user_provisioning_service.record_identity_link_refused(
                                link_user_id, idp.id, idp_audit_actions.IdentityLinkRefusal.LINKED_TO_ANOTHER_ACCOUNT
                            )
                            raise core_exceptions.ConflictError(
                                f"This {idp.name} account is already linked to another user"
                            )

                    # Create the link
                    identity_provider_links_integration.create_user_identity_provider(
                        user_id=link_user_id, idp_id=idp.id, idp_subject=subject, db=db
                    )
                    user_provisioning_service.stage_identity_link(link_user_id, idp.id, db)
                    idp_event_publishers.publish_idp_linked(link_user_id, idp.id, db)
                    # The state records the session that started the link only when the user asked to end the others.
                    if oauth_state.session_id is not None:
                        _stage_other_sessions_ended(link_user_id, oauth_state.session_id, db)

                    user = user_provisioning_service.update_user_from_idp(user, idp, userinfo, db)

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
                return CallbackResult(user=user, userinfo=userinfo, mode="link")
            else:
                # LOGIN MODE: Find or create user and establish session
                try:
                    user = user_provisioning_service.find_or_create_user(idp, subject, userinfo, db)
                except core_exceptions.PermissionDeniedError:
                    _record_login_refusal(
                        jasil_audit.Outcome.DENIED, login_audit_actions.LoginFailureReason.PROVISIONING_REFUSED
                    )
                    raise

                # A new account awaiting verification or approval is committed so the administrator sees it, and
                # the sign-in is refused when the session is created; the tokens are stored with that session.
                db.commit()
                logger.info(
                    "User <username_log_id> authenticated via IdP <name>",
                    extra=core_logger.context(
                        username_log_id=lockout_integration.username_log_identifier(user.username), name=idp.name
                    ),
                )

                return CallbackResult(
                    user=user,
                    userinfo=userinfo,
                    mode="login",
                    redirect_path=redirect_path,
                    token_response=token_response,
                )

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
        oauth_state: oauth_state_schema.StepUpOAuthStateRead,
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
                _record_step_up_refusal(
                    oauth_state, jasil_audit.Outcome.DENIED, login_audit_actions.StepUpFailureReason.NOT_LINKED
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
            _record_step_up_refusal(
                oauth_state, jasil_audit.Outcome.FAILURE, login_audit_actions.StepUpFailureReason.NOT_FRESH
            )
            return identity_provider_utils.build_step_up_result_url(
                self._frontend_host, oauth_state.redirect_path, {"step_up_error": "not_fresh"}
            )
        except core_exceptions.DomainError as err:
            logger.warning(
                "Step-up re-authentication with IdP <name> failed for user <user_id>",
                exc_info=err,
                extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name),
            )
            _record_step_up_refusal(oauth_state, jasil_audit.Outcome.FAILURE, _PROVIDER_ERROR.step_up)
            return self._failure_url(oauth_state)
        except Exception as err:
            # The browser leg always ends in a redirect, so a bug still lands on the failure page, without a ticket.
            logger.error(
                "Unexpected error in step-up re-authentication with IdP <name> for user <user_id>",
                exc_info=err,
                extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name),
            )
            _record_step_up_refusal(oauth_state, jasil_audit.Outcome.FAILURE, _PROVIDER_ERROR.step_up)
            return self._failure_url(oauth_state)
        logger.info(
            "User <user_id> re-authenticated with IdP <name> for <action>",
            extra=core_logger.context(user_id=oauth_state.user_id, name=idp.name, action=oauth_state.action),
        )
        return identity_provider_utils.build_step_up_result_url(
            self._frontend_host, oauth_state.redirect_path, {"step_up_ticket": ticket}
        )

    def _exchange_code(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        oauth_client: OAuth2Client,
        token_endpoint: str,
        code: str,
        code_verifier: str | None,
    ) -> dict[str, Any]:
        """Redeem an authorization code at the provider's token endpoint.

        Args:
            idp: The provider.
            oauth_client: The client that redeems the code.
            token_endpoint: The provider's token endpoint.
            code: The authorization code.
            code_verifier: The PKCE verifier stored with the authorization request.

        Returns:
            The provider's token response.

        Raises:
            UpstreamTimeoutError: If the provider does not answer in time.
            UpstreamError: If the provider cannot be reached, answers with an HTTP error or refuses the code.
            ProcessingError: If the token response is malformed or the token endpoint URL cannot be sent to.
        """
        try:
            return oauth_client.fetch_token(
                token_endpoint,
                grant_type="authorization_code",
                code=code,
                code_verifier=code_verifier,
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
                    f"Identity provider {idp.name} rejected the authentication request. Please contact administrator."
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
        except OAuthError as err:
            # The provider answered with an OAuth error body (invalid_grant, invalid_client, ...).
            logger.warning(
                "IdP <name> refused the token exchange: <error>",
                extra=core_logger.context(name=idp.name, error=err.error),
            )
            raise core_exceptions.UpstreamError(
                f"Identity provider {idp.name} rejected the authentication request. Please try logging in again."
            ) from err
        except (ValueError, TypeError, OverflowError, httpx2.InvalidURL) as err:
            # A body that is not JSON or an expires_in that is not a number (authlib's int()), or a token
            # endpoint URL httpx cannot send to
            logger.debug(
                "Malformed token response or invalid token endpoint for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to complete authentication. Please try again.") from err

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
            UpstreamTimeoutError: If the provider does not answer the code exchange in time.
            UpstreamError: If the provider publishes no issuer or signing keys, cannot be reached, refuses the
                code or returns no ID token.
            ProcessingError: If the token response is malformed or the token endpoint URL cannot be sent to.
            UnauthenticatedError: If the ID token does not verify or names no subject.
            _StaleSignInError: If the ID token does not prove a sign-in within the step-up's limit.
        """
        client_id = self._oidc.decrypt_client_id(idp)
        jwks_uri, issuer = oidc_client_service.require_signing_keys(idp, self._oidc.get_oidc_configuration(idp) or {})
        with self._oidc.create_oauth_client(
            client_id=client_id,
            client_secret=self._oidc.decrypt_client_secret(idp),
            redirect_uri=identity_provider_utils.build_redirect_uri(self._frontend_host, idp.slug),
        ) as oauth_client:
            token_response = self._exchange_code(
                idp, oauth_client, self._oidc.resolve_token_endpoint(idp), code, oauth_state.idp_code_verifier
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
        user: users_schema.UserRead,
        ip_address: str,
        user_agent: str,
        password_hasher: credentials_integration.PasswordHasher,
        oauth_state: oauth_state_schema.OAuthStateRead,
        idp_id: int,
        token_response: dict[str, Any],
        db: Session,
        *,
        idp_sid: str | None,
    ) -> str:
        """Create the token-exchange session for a successful SSO login, with the provider tokens it signed in with.

        The session is for the client type the OAuth state recorded when the sign-in started. The session and the
        provider's sign-in are committed together. Until the token exchange claims the session
        it expires with the OAuth state, which is also when the exchange stops being possible; the exchange then
        gives it its real expiry.

        Args:
            user: The user who signed in.
            ip_address: Client address, recorded on the session.
            user_agent: Client user agent, recorded on the session.
            password_hasher: Hasher for the session's refresh token.
            oauth_state: The OAuth state the token exchange will validate.
            idp_id: The provider the user signed in through.
            token_response: The provider's token response.
            db: Database session.
            idp_sid: The provider session id of the verified ID token, or None when it named none.

        Returns:
            The new session's id.

        Raises:
            SsoSignInRefusedError: If the account is not active, with the login page's code for why.
        """
        try:
            users_integration.require_active_user(user)
        except core_exceptions.PermissionDeniedError as err:
            _record_login_refusal(
                jasil_audit.Outcome.DENIED, login_audit_actions.LoginFailureReason.INACTIVE, user_id=user.id
            )
            raise _inactive_account_refusal(user, db) from err
        user_read = users_schema.UserRead.model_validate(user)
        session_id = str(uuid4())
        sessions_integration.create_session(
            session_id,
            user_read,
            auth_constants.ClientType(oauth_state.client_type),
            ip_address,
            user_agent,
            None,
            password_hasher,
            core_timezone.to_utc_aware(oauth_state.expires_at),
            db,
            oauth_state_id=oauth_state.id,
        )
        self._tokens.store_session_tokens(session_id, user_read.id, idp_id, token_response, db, idp_sid=idp_sid)
        db.commit()
        logger.debug("SSO callback session created", extra=core_logger.context(user_id=user_read.id))
        return session_id


def _inactive_account_refusal(
    user: users_schema.UserRead, db: Session
) -> user_provisioning_service.SsoSignInRefusedError:
    """Return the refusal of an inactive account's sign-in, with the login page's code for what the user can do.

    The user has just proven their identity to the provider, so naming their own account's state reveals nothing
    to anyone else. An account awaiting an administrator's approval is told to wait; one an administrator
    deactivated or a deletion request ended, and any other inactive account, cannot sign in.

    Args:
        user: The inactive account.
        db: Database session.

    Returns:
        The refusal to raise.
    """
    if user.pending_admin_approval and not users_integration.is_deactivated(user.id, db):
        return user_provisioning_service.SsoSignInRefusedError(
            "The account is awaiting administrator approval", login_error="sso_approval_pending"
        )
    return user_provisioning_service.SsoSignInRefusedError(
        "The account is not active", login_error="sso_account_disabled"
    )


def _provider_session_id(claims: dict[str, Any]) -> str | None:
    """Return the provider session id (``sid``) a sign-in's verified ID token named, when it is usable.

    ``OidcClientService.get_userinfo`` takes ``sid`` only from the verified ID token. A value that is not a
    non-empty string of at most ``MAX_SESSION_ID_LENGTH`` characters is not stored, so a back-channel logout can
    name that sign-in only by its subject.

    Args:
        claims: The sign-in's identity claims.

    Returns:
        The ``sid``, or None when the ID token named none or named an unusable one.
    """
    sid = claims.get("sid")
    if isinstance(sid, str) and 0 < len(sid) <= id_token_service.MAX_SESSION_ID_LENGTH:
        return sid
    if sid is not None:
        logger.warning("ID token sid is not a usable string; the sign-in is stored without it")
    return None


def _stage_other_sessions_ended(user_id: int, keep_session_id: str, db: Session) -> None:
    """Stage the end of the user's sessions except the one that started a link, with its audit row.

    Args:
        user_id: ID of the user who linked the provider.
        keep_session_id: The session that started the link, kept.
        db: Database session.
    """
    ended = sessions_integration.delete_sessions_by_user(user_id, db, exclude_session_id=keep_session_id)
    if ended:
        jasil_audit.stage(
            db,
            sessions_audit_actions.SESSION_REVOKE,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
            details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=ended),
        )


def _record_login_refusal(
    outcome: jasil_audit.Outcome, reason: login_audit_actions.LoginFailureReason, *, user_id: int | None = None
) -> None:
    """Audit a refused SSO sign-in, on its own transaction because the callback answers with a redirect.

    Args:
        outcome: ``FAILURE`` for a bad token or state, ``DENIED`` for a refusal by policy.
        reason: Why the sign-in was refused.
        user_id: The account the sign-in named, or None when none was matched.
    """
    login_audit_integration.record_login_refusal(
        login_audit_actions.LoginMethod.IDENTITY_PROVIDER, outcome, reason, user_id=user_id
    )


@dataclass(frozen=True)
class _ProviderFailure:
    """A refusal caused by the provider, in the reason each flow's audit action names it.

    Attributes:
        login: The reason of an ``auth.session.login`` row.
        link: The reason of an ``auth.identity_link.link`` row.
        step_up: The reason of an ``auth.step_up.verify`` row.
    """

    login: login_audit_actions.LoginFailureReason
    link: idp_audit_actions.IdentityLinkRefusal
    step_up: login_audit_actions.StepUpFailureReason


_PROVIDER_ERROR = _ProviderFailure(
    login_audit_actions.LoginFailureReason.PROVIDER_ERROR,
    idp_audit_actions.IdentityLinkRefusal.PROVIDER_ERROR,
    login_audit_actions.StepUpFailureReason.PROVIDER_FAILURE,
)
_TOKEN_EXCHANGE_FAILED = _ProviderFailure(
    login_audit_actions.LoginFailureReason.TOKEN_EXCHANGE_FAILED,
    idp_audit_actions.IdentityLinkRefusal.TOKEN_EXCHANGE_FAILED,
    login_audit_actions.StepUpFailureReason.PROVIDER_FAILURE,
)
_NO_SUBJECT = _ProviderFailure(
    login_audit_actions.LoginFailureReason.NO_SUBJECT,
    idp_audit_actions.IdentityLinkRefusal.NO_SUBJECT,
    login_audit_actions.StepUpFailureReason.PROVIDER_FAILURE,
)


def _proven_actor(oauth_state: oauth_state_schema.OAuthStateRead) -> AbstractContextManager[None]:
    """Return the audit context for rows about a link or step-up whose browser the callback has proven.

    Args:
        oauth_state: The claimed state, whose user started the flow.

    Returns:
        A context that names the state's user as the actor, or one that changes nothing when it names none.
    """
    if oauth_state.user_id is None:
        return nullcontext()
    return login_audit_integration.acting_as_user(oauth_state.user_id)


def _record_step_up_refusal(
    oauth_state: oauth_state_schema.OAuthStateRead,
    outcome: jasil_audit.Outcome,
    reason: login_audit_actions.StepUpFailureReason,
    *,
    browser_proven: bool = True,
) -> None:
    """Audit a refused identity-provider step-up, on its own transaction because the callback redirects.

    Args:
        oauth_state: The step-up state, whose user is the target.
        outcome: ``FAILURE`` for a provider, freshness or state failure, ``DENIED`` for a refusal by policy.
        reason: Why the step-up was refused.
        browser_proven: Whether the callback came from the browser that started the step-up. When it did not,
            the user is only the target: they are the victim, not the actor.
    """
    with _proven_actor(oauth_state) if browser_proven else nullcontext():
        jasil_audit.record_detached(
            login_audit_actions.STEP_UP_VERIFY,
            outcome=outcome,
            **login_audit_integration.user_target(oauth_state.user_id),
            details=login_audit_actions.StepUpDetails(
                method=login_audit_actions.StepUpMethod.IDENTITY_PROVIDER, reason=reason
            ),
        )


def _is_account_flow(oauth_state: oauth_state_schema.OAuthStateRead) -> bool:
    """Tell whether a state belongs to a link or step-up of a known user; one that names no user is a sign-in."""
    return oauth_state.purpose != oauth_state_constants.OAuthStatePurpose.LOGIN and oauth_state.user_id is not None


def _record_state_refusal(idp_id: int, oauth_state: oauth_state_schema.OAuthStateRead | None) -> None:
    """Audit a callback whose OAuth state was refused, as the flow the state belongs to.

    A state nobody can find could have started a sign-in, so it is recorded as one. The row is anonymous: the
    refusal does not prove the callback comes from the browser that started the flow.

    Args:
        idp_id: The provider the callback came to.
        oauth_state: The state the callback named, or None when none was found.
    """
    if oauth_state is None or not _is_account_flow(oauth_state):
        _record_login_refusal(jasil_audit.Outcome.FAILURE, login_audit_actions.LoginFailureReason.INVALID_STATE)
    elif oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.LINK and oauth_state.user_id is not None:
        user_provisioning_service.record_identity_link_refused(
            oauth_state.user_id,
            idp_id,
            idp_audit_actions.IdentityLinkRefusal.INVALID_STATE,
            jasil_audit.Outcome.FAILURE,
        )
    else:
        _record_step_up_refusal(
            oauth_state,
            jasil_audit.Outcome.FAILURE,
            login_audit_actions.StepUpFailureReason.INVALID_STATE,
            browser_proven=False,
        )


def _record_browser_mismatch(idp_id: int, oauth_state: oauth_state_schema.OAuthStateRead) -> None:
    """Audit a link or step-up callback that came from a browser other than the one that started it.

    The user is only the target: that browser is not theirs, so they are not named as the actor.

    Args:
        idp_id: The provider the callback came to.
        oauth_state: The link or step-up state.
    """
    if oauth_state.user_id is None:
        return
    if oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.LINK:
        user_provisioning_service.record_identity_link_refused(
            oauth_state.user_id, idp_id, idp_audit_actions.IdentityLinkRefusal.BROWSER_MISMATCH
        )
    else:
        _record_step_up_refusal(
            oauth_state,
            jasil_audit.Outcome.DENIED,
            login_audit_actions.StepUpFailureReason.BROWSER_MISMATCH,
            browser_proven=False,
        )


def _record_provider_refusal(
    idp_id: int, oauth_state: oauth_state_schema.OAuthStateRead, failure: _ProviderFailure
) -> None:
    """Audit a callback the provider's answer made fail, as the flow the state belongs to.

    The state was claimed in the browser that started the flow, so a link or step-up row names its user as the
    actor.

    Args:
        idp_id: The provider that failed.
        oauth_state: The claimed state.
        failure: The provider failure.
    """
    if not _is_account_flow(oauth_state):
        _record_login_refusal(jasil_audit.Outcome.FAILURE, failure.login)
    elif oauth_state.purpose == oauth_state_constants.OAuthStatePurpose.LINK and oauth_state.user_id is not None:
        with _proven_actor(oauth_state):
            user_provisioning_service.record_identity_link_refused(
                oauth_state.user_id, idp_id, failure.link, jasil_audit.Outcome.FAILURE
            )
    else:
        _record_step_up_refusal(oauth_state, jasil_audit.Outcome.FAILURE, failure.step_up)


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
