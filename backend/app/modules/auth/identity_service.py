"""IdentityService Protocol and DefaultIdentityService implementation.

Defines the ``IdentityService`` boundary type that non-auth modules must use
to consume identity.  The boundary hides the concrete helpers
(:mod:`modules.auth._internal.internal_dependencies`, :mod:`modules.auth._internal.password_hasher`,
:mod:`modules.auth._internal.token_manager`) from external callers and makes them mockable in
isolation.

Transaction contract
--------------------
``IdentityService`` owns no transaction policy of its own. It delegates
database work to auth CRUD helpers, and those helpers own their module's
commit/refresh behaviour. Callers that need a multi-step atomic workflow
must use or introduce CRUD helpers designed for that workflow.

Request-state caching
---------------------
The resolved :class:`~auth.principal.Principal` should be stored on
``request.state.principal`` after the first resolution so that
multiple FastAPI dependencies in the same request do not trigger
duplicate database lookups.

Usage
-----
Inject via the ``get_identity_service`` FastAPI dependency.  A new
:class:`DefaultIdentityService` instance is returned per request;
never use a module-level singleton.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Protocol, runtime_checkable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import modules.auth._internal.password_hasher as auth_password_hasher
import modules.auth._internal.services.account_security_service as auth_account_security_service
import modules.auth._internal.services.identity_link_service as auth_identity_link_service
import modules.auth._internal.services.mfa_workflow as auth_mfa_workflow
import modules.auth._internal.token_manager as auth_token_manager
import modules.auth.api_keys.crud as auth_api_keys_crud
import modules.auth.api_keys.utils as auth_api_keys_utils
import modules.auth.credentials.crud as auth_credentials_crud
import modules.auth.mfa.crud as auth_mfa_crud
import modules.auth.sessions.crud as auth_sessions_crud
import modules.auth.utils as auth_utils
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils
from modules.auth.principal import (
    AccessTokenCred,
    ApiKeyCred,
    OAuthCred,
    PasswordCred,
    Principal,
    SessionCookieCred,
)

if TYPE_CHECKING:
    import modules.auth._internal.security_stores as auth_security_stores
    import modules.auth.identity_providers.link_tokens.schema as auth_idp_link_tokens_schema
    import modules.auth.identity_providers.links.schema as auth_identity_links_schema
    import modules.auth.mfa.backup_codes.schema as auth_mfa_backup_codes_schema
    import modules.auth.mfa.schema as auth_mfa_schema
    import modules.auth.mfa.setup_store as auth_mfa_setup_store
    import modules.auth.sessions.schema as auth_sessions_schema

__all__ = [
    "DefaultIdentityService",
    "IdentityService",
    "get_identity_service",
]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class IdentityService(Protocol):
    """Typed contract for the auth boundary.

    All methods except :meth:`check_scope` may raise
    :class:`~fastapi.HTTPException` on invalid or expired
    credentials. Methods delegate database operations to auth
    CRUD helpers, including those helpers' commit behaviour.
    """

    def authenticate_password(
        self,
        username: str,
        password: str,
    ) -> Principal:
        """Verify username/password and return a Principal.

        Args:
            username: The username supplied by the caller.
            password: The plaintext password to verify.

        Returns:
            Principal: Resolved principal with a
                :class:`~auth.principal.PasswordCred`.

        Raises:
            HTTPException: 401 if the credentials are
                invalid or the account does not exist.
        """
        ...

    def resolve_from_access_token(
        self,
        access_token: str,
    ) -> Principal:
        """Validate a JWT access token and return a Principal.

        Args:
            access_token: The raw JWT string from the
                Authorization header.

        Returns:
            Principal: Resolved principal with an
                :class:`~auth.principal.AccessTokenCred`.

        Raises:
            HTTPException: 401 if the token is expired,
                invalid, or the user is not found.
        """
        ...

    def resolve_from_api_key(
        self,
        raw_key: str,
        request: Request,
    ) -> Principal:
        """Validate a raw API key and return a Principal.

        Args:
            raw_key: The plain-text API key from the
                ``X-API-Key`` header or ``?api_key=``
                query parameter.
            request: The current HTTP request (used for
                audit logging).

        Returns:
            Principal: Resolved principal with an
                :class:`~auth.principal.ApiKeyCred`.

        Raises:
            HTTPException: 401 if the key is not found,
                revoked, or expired.
        """
        ...

    def resolve_from_session_cookie(
        self,
        session_id: str,
    ) -> Principal:
        """Validate a session ID and return a Principal.

        Args:
            session_id: The session identifier from the
                cookie or token ``sid`` claim.

        Returns:
            Principal: Resolved principal with a
                :class:`~auth.principal.SessionCookieCred`.

        Raises:
            HTTPException: 401 if the session is not
                found or has expired.
        """
        ...

    def issue_token_pair(
        self,
        user: users_schema.UsersRead,
        session_id: str | None = None,
    ) -> tuple[str, datetime, str, datetime, str, str]:
        """Issue an access/refresh token pair for a user.

        Args:
            user: The validated user object.
            session_id: Optional existing session
                identifier; a new UUID is generated
                when ``None``.

        Returns:
            tuple: ``(session_id, access_token_exp,
                access_token, refresh_token_exp,
                refresh_token, csrf_token)``.
        """
        ...

    def revoke_session(
        self,
        session_id: str,
        user_id: int,
    ) -> None:
        """Revoke and delete a session.

        Args:
            session_id: The session to revoke.
            user_id: Owner of the session (used to
                prevent cross-user revocations).

        Raises:
            HTTPException: 404 if the session is not
                found for this user.
        """
        ...

    def check_scope(
        self,
        principal: Principal,
        required_scopes: frozenset[str],
    ) -> None:
        """Assert that the principal holds all required scopes.

        Args:
            principal: The authenticated principal.
            required_scopes: Scope strings that must all
                be present in ``principal.scopes``.

        Raises:
            HTTPException: 403 if any required scope is
                missing.
        """
        ...

    def validate_and_hash_password(
        self,
        password: str,
        min_length: int,
        password_type: str,
    ) -> str:
        """Validate password policy and return a secure hash.

        Args:
            password: Plaintext password to validate and hash.
            min_length: Minimum configured password length.
            password_type: Configured password policy type.

        Returns:
            Secure password hash.

        Raises:
            HTTPException: 400 if the password policy fails.
        """
        ...

    def hash_password(self, password: str) -> str:
        """Return a secure hash for a trusted generated secret.

        Args:
            password: Plaintext password or generated secret.

        Returns:
            Secure hash.
        """
        ...

    def verify_password(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        """Verify a plaintext password against a stored hash.

        Args:
            password: Plaintext password supplied by the caller.
            password_hash: Stored password hash.

        Returns:
            True if the password matches, False otherwise.
        """
        ...

    def get_password_hash(self, user_id: int) -> str | None:
        """Return a user's stored local password hash, or ``None``.

        ``None`` means the account has no local password (for example an
        SSO-only account).

        Args:
            user_id: ID of the user to read the credential for.

        Returns:
            The stored password hash, or ``None`` if no credential exists.
        """
        ...

    def has_local_password(self, user_id: int) -> bool:
        """Return whether a user has a local password credential.

        ``False`` means the account is SSO-only (no row in
        ``users_local_credentials``). The password hash itself is never
        exposed; only this derived boolean is returned.

        Args:
            user_id: ID of the user to check the credential for.

        Returns:
            True if a local credential row exists, False otherwise.
        """
        ...

    def set_local_password_hash(self, user_id: int, password_hash: str) -> None:
        """Insert or update a user's local password hash.

        Args:
            user_id: ID of the user to write the credential for.
            password_hash: Argon2/bcrypt password hash to store.

        Returns:
            None.
        """
        ...

    def clear_local_password(self, user_id: int) -> None:
        """Remove a user's local password credential, if present.

        Args:
            user_id: ID of the user whose credential should be removed.

        Returns:
            None.
        """
        ...

    def initialize_user_mfa(self, user_id: int) -> None:
        """Create the default (disabled) MFA row for a new user.

        Establishes the 1:1 ``users``↔``users_mfa`` invariant so non-auth
        modules never touch the auth-owned MFA table directly.

        Args:
            user_id: ID of the newly created user.

        Returns:
            None.
        """
        ...

    # ------------------------------------------------------------------
    # Account-security workflows
    #
    # These are higher-level, route-facing workflows (sessions, password
    # change, MFA lifecycle, IdP linking) consumed by non-auth routers
    # (e.g. ``modules.users.users_profile``). They are part of the public auth
    # boundary: implementations live in ``modules.auth._internal.services.*`` and are reached
    # only through this contract, never imported directly by non-auth code.
    # ------------------------------------------------------------------

    def get_user_sessions(self, user_id: int) -> list[auth_sessions_schema.UsersSessionsRead]:
        """Return the authenticated user's active sessions.

        Args:
            user_id: ID of the authenticated user.

        Returns:
            List of the user's active sessions (empty in the demo environment).
        """
        ...

    def delete_user_session(self, session_id: str, user_id: int) -> None:
        """Delete one of the authenticated user's own sessions.

        Args:
            session_id: ID of the session to delete.
            user_id: Owner of the session.

        Returns:
            None.
        """
        ...

    def delete_other_user_sessions(self, user_id: int, current_session_id: str) -> None:
        """Delete all of the authenticated user's sessions except the current one.

        Args:
            user_id: Owner of the sessions.
            current_session_id: The caller's session, left intact.

        Returns:
            None.
        """
        ...

    def change_own_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        mfa_code: str | None,
        step_up_store: auth_security_stores.StepUpStore,
        revoke_other_sessions: bool = False,
        current_session_id: str | None = None,
    ) -> None:
        """Change the authenticated user's password after step-up verification.

        Args:
            user_id: ID of the authenticated user.
            current_password: Current password supplied for step-up.
            new_password: New plaintext password to store.
            mfa_code: Optional MFA code supplied for step-up.
            step_up_store: Step-up lockout store.
            revoke_other_sessions: When True, revoke all of the user's
                other sessions (keeping ``current_session_id``).
            current_session_id: Caller's session ID, preserved when
                ``revoke_other_sessions`` is True.

        Returns:
            None.

        Raises:
            HTTPException: If step-up verification or persistence fails.
        """
        ...

    def change_managed_user_password(self, user_id: int, new_password: str) -> None:
        """Change a managed user's password and revoke their auth state.

        Args:
            user_id: ID of the user whose password is changed.
            new_password: New plaintext password to store.

        Returns:
            None.

        Raises:
            HTTPException: If password persistence fails.
        """
        ...

    def get_mfa_status(self, user_id: int) -> auth_mfa_schema.MFAStatusResponse:
        """Return whether MFA is enabled for the user.

        Args:
            user_id: ID of the authenticated user.

        Returns:
            MFA status response.
        """
        ...

    def get_backup_code_status(self, user_id: int) -> auth_mfa_backup_codes_schema.MFABackupCodeStatus:
        """Return the user's MFA backup-code status.

        Args:
            user_id: ID of the authenticated user.

        Returns:
            Backup-code status response.
        """
        ...

    def setup_mfa(
        self,
        user_id: int,
        mfa_secret_store: auth_mfa_setup_store.MFASecretStoreBackend,
    ) -> auth_mfa_schema.MFASetupResponse:
        """Create MFA setup material and store the pending setup secret.

        Args:
            user_id: ID of the authenticated user.
            mfa_secret_store: Pending MFA setup-secret store.

        Returns:
            MFA setup response with QR/secret material.
        """
        ...

    def enable_mfa(
        self,
        request: auth_mfa_schema.MFASetupRequest,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
        mfa_secret_store: auth_mfa_setup_store.MFASecretStoreBackend,
    ) -> dict:
        """Enable MFA using the pending secret and a verification code.

        Args:
            request: MFA setup request carrying credentials and code.
            user_id: ID of the authenticated user.
            step_up_store: Step-up lockout store.
            mfa_secret_store: Pending MFA setup-secret store.

        Returns:
            Confirmation payload including backup codes.

        Raises:
            HTTPException: If step-up or verification fails.
        """
        ...

    def disable_mfa(
        self,
        request: auth_mfa_schema.MFADisableRequest,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> dict:
        """Disable MFA after step-up verification.

        Args:
            request: MFA disable request carrying credentials and code.
            user_id: ID of the authenticated user.
            step_up_store: Step-up lockout store.

        Returns:
            Confirmation payload.

        Raises:
            HTTPException: If step-up verification fails.
        """
        ...

    def verify_mfa(self, request: auth_mfa_schema.MFARequest, user_id: int) -> dict:
        """Verify an MFA code for the authenticated user.

        Args:
            request: MFA request carrying the code to verify.
            user_id: ID of the authenticated user.

        Returns:
            Confirmation payload.

        Raises:
            HTTPException: If the code is invalid.
        """
        ...

    def generate_backup_codes(
        self,
        step_up: users_schema.StepUpVerification,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> auth_mfa_backup_codes_schema.MFABackupCodesResponse:
        """Generate new backup codes for an MFA-enabled account.

        Args:
            step_up: Step-up verification payload.
            user_id: ID of the authenticated user.
            step_up_store: Step-up lockout store.

        Returns:
            Newly generated backup codes.

        Raises:
            HTTPException: If MFA is disabled or step-up fails.
        """
        ...

    def generate_link_token(
        self,
        idp_id: int,
        link_request: auth_idp_link_tokens_schema.IdpLinkTokenRequest,
        request: Request,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> auth_idp_link_tokens_schema.IdpLinkTokenResponse:
        """Generate a one-time IdP link token after step-up verification.

        Args:
            idp_id: ID of the identity provider to link.
            link_request: Link-token request payload (credentials).
            request: Current HTTP request (for client IP).
            user_id: ID of the authenticated user.
            step_up_store: Step-up lockout store.

        Returns:
            The generated one-time link token.

        Raises:
            HTTPException: If step-up fails, the IdP is missing/disabled, or
                already linked.
        """
        ...

    def delete_identity_provider_link(
        self,
        idp_id: int,
        step_up: users_schema.StepUpVerification,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> None:
        """Unlink an IdP while enforcing anti-lockout checks.

        Args:
            idp_id: ID of the identity provider to unlink.
            step_up: Step-up verification payload.
            user_id: ID of the authenticated user.
            step_up_store: Step-up lockout store.

        Returns:
            None.

        Raises:
            HTTPException: If step-up fails, the link is missing, or unlinking
                would remove the last authentication method.
        """
        ...

    def get_user_identity_provider_links(
        self,
        user_id: int,
    ) -> list[auth_identity_links_schema.UsersIdentityProviderResponse]:
        """Return enriched identity-provider links for the user.

        Args:
            user_id: ID of the authenticated user.

        Returns:
            List of enriched identity-provider link responses.
        """
        ...

    def admin_delete_identity_provider_link(
        self,
        user_id: int,
        idp_id: int,
    ) -> None:
        """Unlink an IdP from a user as an administrator (no step-up).

        Args:
            user_id: ID of the user to unlink the IdP from.
            idp_id: ID of the identity provider to unlink.

        Returns:
            None.

        Raises:
            HTTPException: If the IdP or the link is missing.
        """
        ...

    def validate_and_claim_browser_link_token(
        self,
        link_token: str,
        idp_id: int,
        client_ip: str | None,
    ) -> int:
        """Validate, IP-check, and atomically claim a browser-redirect link token.

        Args:
            link_token: Plaintext one-time link token from the query string.
            idp_id: The identity provider ID expected in the token.
            client_ip: Caller IP address for the soft IP-match check.

        Returns:
            The user ID encoded in the token.

        Raises:
            HTTPException: 401/400/409 on invalid, replayed, or conflicting tokens.
        """
        ...

    def get_identity_link_counts_for_users(self, user_ids: list[int]) -> dict[int, int]:
        """Return identity-link count per user ID in a single grouped query.

        Args:
            user_ids: List of user IDs to query.

        Returns:
            Mapping of user_id to link count (users with no links are absent).
        """
        ...


# ---------------------------------------------------------------------------
# Default implementation
# ---------------------------------------------------------------------------


class DefaultIdentityService:
    """Concrete ``IdentityService`` that delegates to existing helpers.

    Constructor injects all per-request dependencies explicitly so that
    each method is testable in isolation.

    Transaction contract: this service does not mutate ORM state
    directly. It delegates database work to auth CRUD helpers, which
    own their module-level commit and refresh behaviour.

    Attributes:
        _db: SQLAlchemy database session for this request.
        _token_manager: JWT token manager.
        _password_hasher: Password hasher/verifier.
    """

    def __init__(
        self,
        db: Session,
        token_manager: auth_token_manager.TokenManager,
        password_hasher: auth_password_hasher.PasswordHasher,
    ) -> None:
        """
        Initialise the service with per-request dependencies.

        Args:
            db: SQLAlchemy database session.
            token_manager: Configured JWT token manager.
            password_hasher: Argon2/bcrypt password hasher.
        """
        self._db = db
        self._token_manager = token_manager
        self._password_hasher = password_hasher

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_principal(
        self,
        user: object,
        scopes: list[str],
        credential: (PasswordCred | AccessTokenCred | ApiKeyCred | SessionCookieCred | OAuthCred),
    ) -> Principal:
        """Build a ``Principal`` from an ORM user row.

        Args:
            user: SQLAlchemy ``Users`` model instance.
            scopes: List of granted OAuth2 scope strings.
            credential: Typed credential variant.

        Returns:
            Principal: Frozen principal ready to cache on
                ``request.state``.
        """
        return Principal(
            user_id=user.id,  # type: ignore[attr-defined]
            username=user.username,  # type: ignore[attr-defined]
            email=user.email,  # type: ignore[attr-defined]
            is_active=bool(user.active),  # type: ignore[attr-defined]
            is_superuser=(
                user.access_type == "admin"  # type: ignore[attr-defined]
            ),
            scopes=frozenset(scopes),
            credential=credential,
        )

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def authenticate_password(
        self,
        username: str,
        password: str,
    ) -> Principal:
        """Verify username/password and return a Principal.

        Args:
            username: The username supplied by the caller.
            password: The plaintext password to verify.

        Returns:
            Principal: Resolved principal with a
                :class:`~auth.principal.PasswordCred`.

        Raises:
            HTTPException: 401 if the credentials are
                invalid or the account does not exist.
        """
        user = auth_utils.authenticate_user(
            username,
            password,
            self._password_hasher,
            self._db,
        )
        # Scopes are determined by the token-issuing step;
        # at password-auth time we return an empty set so
        # callers know authentication succeeded but must
        # call issue_token_pair to get scoped tokens.
        return self._build_principal(user, [], PasswordCred(username=username))

    def resolve_from_access_token(
        self,
        access_token: str,
    ) -> Principal:
        """Validate a JWT access token and return a Principal.

        Args:
            access_token: The raw JWT string from the
                Authorization header.

        Returns:
            Principal: Resolved principal with an
                :class:`~auth.principal.AccessTokenCred`.

        Raises:
            HTTPException: 401 if the token is expired,
                invalid, or the user is not found.
        """
        self._token_manager.validate_access_expiration_logged(access_token)

        sub = self._token_manager.get_token_claim(access_token, "sub")
        if not isinstance(sub, int):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: 'sub' claim must be an integer",
            )

        scope = self._token_manager.get_token_claim(access_token, "scope")
        if not isinstance(scope, list):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: 'scope' claim must be a list",
            )

        sid = self._token_manager.get_token_claim(access_token, "sid")
        if not isinstance(sid, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=("Invalid token: 'sid' claim must be a string"),
            )

        user = users_utils.get_user_by_id_or_404(sub, self._db)
        users_utils.check_user_is_active(user)

        return self._build_principal(
            user,
            scope,
            AccessTokenCred(session_id=sid),
        )

    def resolve_from_api_key(
        self,
        raw_key: str,
        request: Request,
    ) -> Principal:
        """Validate a raw API key and return a Principal.

        Args:
            raw_key: The plain-text API key from the
                ``X-API-Key`` header or ``?api_key=``
                query parameter.
            request: The current HTTP request (used for
                audit logging).

        Returns:
            Principal: Resolved principal with an
                :class:`~auth.principal.ApiKeyCred`.

        Raises:
            HTTPException: 401 if the key is not found,
                revoked, or expired.
        """
        computed_hash = auth_api_keys_utils.hash_api_key(raw_key)
        db_key = auth_api_keys_crud.get_api_key_by_hash(computed_hash, self._db)

        # Constant-time comparison prevents timing attacks
        # even when the key is not found.
        stored_hash = db_key.key_hash if db_key else ("0" * 64)
        if not hmac.compare_digest(stored_hash, computed_hash):
            db_key = None

        if db_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        user = users_utils.get_user_by_id_or_404(db_key.user_id, self._db)
        users_utils.check_user_is_active(user)

        if not db_key.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        if db_key.expires_at is not None and datetime.now(UTC) > db_key.expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Best-effort last_used_at update; never fails the request.
        try:
            auth_api_keys_crud.update_last_used(db_key.id, self._db)
        except SQLAlchemyError as err:
            core_logger.print_to_log(
                f"Failed to update last_used_at for API key {db_key.id}: {err}",
                "warning",
                exc=err,
            )

        core_logger.print_to_log(
            "API key authenticated",
            "info",
            context={
                "key_prefix": db_key.key_prefix,
                "user_id": db_key.user_id,
                "endpoint": request.url.path,
                "ip": (request.client.host if request.client else "unknown"),
            },
        )

        scopes = auth_api_keys_utils.json_to_scopes(db_key.scopes)
        return self._build_principal(
            user,
            scopes,
            ApiKeyCred(
                api_key_id=db_key.id,
                key_prefix=db_key.key_prefix,
            ),
        )

    def resolve_from_session_cookie(
        self,
        session_id: str,
    ) -> Principal:
        """Validate a session ID and return a Principal.

        Args:
            session_id: The session identifier from the
                cookie or token ``sid`` claim.

        Returns:
            Principal: Resolved principal with a
                :class:`~auth.principal.SessionCookieCred`.

        Raises:
            HTTPException: 401 if the session is not
                found or has expired.
        """
        db_session = auth_sessions_crud.get_session_by_id_not_expired(session_id, self._db)
        if db_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found or expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = users_utils.get_user_by_id_or_404(db_session.user_id, self._db)
        users_utils.check_user_is_active(user)

        return self._build_principal(
            user,
            [],
            SessionCookieCred(session_id=session_id),
        )

    def issue_token_pair(
        self,
        user: users_schema.UsersRead,
        session_id: str | None = None,
    ) -> tuple[str, datetime, str, datetime, str, str]:
        """Issue an access/refresh token pair for a user.

        Args:
            user: The validated user object.
            session_id: Optional existing session
                identifier; a new UUID is generated
                when ``None``.

        Returns:
            tuple: ``(session_id, access_token_exp,
                access_token, refresh_token_exp,
                refresh_token, csrf_token)``.
        """
        return auth_utils.create_tokens(user, self._token_manager, session_id)

    def revoke_session(
        self,
        session_id: str,
        user_id: int,
    ) -> None:
        """Revoke and delete a session.

        Args:
            session_id: The session to revoke.
            user_id: Owner of the session (used to
                prevent cross-user revocations).

        Raises:
            HTTPException: 404 if the session is not
                found for this user.
        """
        auth_sessions_crud.delete_session(session_id, user_id, self._db)

    def check_scope(
        self,
        principal: Principal,
        required_scopes: frozenset[str],
    ) -> None:
        """Assert that the principal holds all required scopes.

        Args:
            principal: The authenticated principal.
            required_scopes: Scope strings that must all
                be present in ``principal.scopes``.

        Raises:
            HTTPException: 403 if any required scope is
                missing.
        """
        missing = required_scopes - principal.scopes
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Unauthorized Access - Missing permissions: {missing}"),
            )

    def validate_and_hash_password(
        self,
        password: str,
        min_length: int,
        password_type: str,
    ) -> str:
        """Validate password policy and return a secure hash.

        Args:
            password: Plaintext password to validate and hash.
            min_length: Minimum configured password length.
            password_type: Configured password policy type.

        Returns:
            Secure password hash.

        Raises:
            HTTPException: 400 if the password policy fails.
        """
        try:
            self._password_hasher.validate_password(
                password,
                min_length,
                password_type,
            )
        except auth_password_hasher.PasswordPolicyError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            ) from err
        return self._password_hasher.hash_password(password)

    def hash_password(self, password: str) -> str:
        """Return a secure hash for a trusted generated secret.

        Args:
            password: Plaintext password or generated secret.

        Returns:
            Secure hash.
        """
        return self._password_hasher.hash_password(password)

    def verify_password(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        """Verify a plaintext password against a stored hash.

        Args:
            password: Plaintext password supplied by the caller.
            password_hash: Stored password hash.

        Returns:
            True if the password matches, False otherwise.
        """
        return self._password_hasher.verify_password(password, password_hash)

    def get_password_hash(self, user_id: int) -> str | None:
        """Return a user's stored local password hash, or ``None``.

        ``None`` means the account has no local password (for example an
        SSO-only account).

        Args:
            user_id: ID of the user to read the credential for.

        Returns:
            The stored password hash, or ``None`` if no credential exists.
        """
        credential = auth_credentials_crud.get_credential(user_id, self._db)
        return credential.password_hash if credential is not None else None

    def has_local_password(self, user_id: int) -> bool:
        """Return whether a user has a local password credential.

        ``False`` means the account is SSO-only (no row in
        ``users_local_credentials``). The password hash itself is never
        exposed; only this derived boolean is returned.

        Args:
            user_id: ID of the user to check the credential for.

        Returns:
            True if a local credential row exists, False otherwise.
        """
        return auth_credentials_crud.get_credential(user_id, self._db) is not None

    def set_local_password_hash(self, user_id: int, password_hash: str) -> None:
        """Insert or update a user's local password hash.

        Args:
            user_id: ID of the user to write the credential for.
            password_hash: Argon2/bcrypt password hash to store.

        Returns:
            None.
        """
        auth_credentials_crud.upsert_password_hash(user_id, password_hash, self._db)

    def clear_local_password(self, user_id: int) -> None:
        """Remove a user's local password credential, if present.

        Args:
            user_id: ID of the user whose credential should be removed.

        Returns:
            None.
        """
        auth_credentials_crud.delete_credential(user_id, self._db)

    def initialize_user_mfa(self, user_id: int) -> None:
        """Create the default (disabled) MFA row for a new user.

        Establishes the 1:1 ``users``↔``users_mfa`` invariant so non-auth
        modules never touch the auth-owned MFA table directly.

        Args:
            user_id: ID of the newly created user.

        Returns:
            None.
        """
        auth_mfa_crud.create_users_mfa_row(user_id, self._db)

    # ------------------------------------------------------------------
    # Account-security workflows (delegate to auth._internal.services.*)
    # ------------------------------------------------------------------

    def get_user_sessions(self, user_id: int) -> list[auth_sessions_schema.UsersSessionsRead]:
        """Return the authenticated user's active sessions."""
        return auth_account_security_service.get_user_sessions(user_id, self._db)

    def delete_user_session(self, session_id: str, user_id: int) -> None:
        """Delete one of the authenticated user's own sessions."""
        auth_account_security_service.delete_user_session(session_id, user_id, self._db)

    def delete_other_user_sessions(self, user_id: int, current_session_id: str) -> None:
        """Delete all of the authenticated user's sessions except the current one."""
        auth_account_security_service.delete_other_user_sessions(
            user_id,
            current_session_id,
            self._db,
        )

    def change_own_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        mfa_code: str | None,
        step_up_store: auth_security_stores.StepUpStore,
        revoke_other_sessions: bool = False,
        current_session_id: str | None = None,
    ) -> None:
        """Change the authenticated user's password after step-up verification."""
        auth_account_security_service.change_own_password(
            user_id,
            current_password,
            new_password,
            mfa_code,
            self,
            step_up_store,
            self._db,
            revoke_other_sessions=revoke_other_sessions,
            current_session_id=current_session_id,
        )

    def change_managed_user_password(self, user_id: int, new_password: str) -> None:
        """Change a managed user's password and revoke their auth state."""
        auth_account_security_service.change_managed_user_password(
            user_id,
            new_password,
            self,
            self._db,
        )

    def get_mfa_status(self, user_id: int) -> auth_mfa_schema.MFAStatusResponse:
        """Return whether MFA is enabled for the user."""
        return auth_mfa_workflow.get_mfa_status(user_id, self._db)

    def get_backup_code_status(self, user_id: int) -> auth_mfa_backup_codes_schema.MFABackupCodeStatus:
        """Return the user's MFA backup-code status."""
        return auth_mfa_workflow.get_backup_code_status(user_id, self._db)

    def setup_mfa(
        self,
        user_id: int,
        mfa_secret_store: auth_mfa_setup_store.MFASecretStoreBackend,
    ) -> auth_mfa_schema.MFASetupResponse:
        """Create MFA setup material and store the pending setup secret."""
        return auth_mfa_workflow.setup_mfa(user_id, self._db, mfa_secret_store)

    def enable_mfa(
        self,
        request: auth_mfa_schema.MFASetupRequest,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
        mfa_secret_store: auth_mfa_setup_store.MFASecretStoreBackend,
    ) -> dict:
        """Enable MFA using the pending secret and a verification code."""
        return auth_mfa_workflow.enable_mfa(
            request,
            user_id,
            self,
            step_up_store,
            self._db,
            mfa_secret_store,
        )

    def disable_mfa(
        self,
        request: auth_mfa_schema.MFADisableRequest,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> dict:
        """Disable MFA after step-up verification."""
        return auth_mfa_workflow.disable_mfa(request, user_id, self, step_up_store, self._db)

    def verify_mfa(self, request: auth_mfa_schema.MFARequest, user_id: int) -> dict:
        """Verify an MFA code for the authenticated user."""
        return auth_mfa_workflow.verify_mfa(request, user_id, self, self._db)

    def generate_backup_codes(
        self,
        step_up: users_schema.StepUpVerification,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> auth_mfa_backup_codes_schema.MFABackupCodesResponse:
        """Generate new backup codes for an MFA-enabled account."""
        return auth_mfa_workflow.generate_backup_codes(step_up, user_id, self, step_up_store, self._db)

    def generate_link_token(
        self,
        idp_id: int,
        link_request: auth_idp_link_tokens_schema.IdpLinkTokenRequest,
        request: Request,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> auth_idp_link_tokens_schema.IdpLinkTokenResponse:
        """Generate a one-time IdP link token after step-up verification."""
        return auth_identity_link_service.generate_link_token(
            idp_id,
            link_request,
            request,
            user_id,
            self,
            step_up_store,
            self._db,
        )

    def delete_identity_provider_link(
        self,
        idp_id: int,
        step_up: users_schema.StepUpVerification,
        user_id: int,
        step_up_store: auth_security_stores.StepUpStore,
    ) -> None:
        """Unlink an IdP while enforcing anti-lockout checks."""
        auth_identity_link_service.delete_identity_provider_link(
            idp_id,
            step_up,
            user_id,
            self,
            step_up_store,
            self._db,
        )

    def get_user_identity_provider_links(
        self,
        user_id: int,
    ) -> list[auth_identity_links_schema.UsersIdentityProviderResponse]:
        """Return enriched identity-provider links for the user."""
        return auth_identity_link_service.get_user_identity_provider_links(user_id, self._db)

    def admin_delete_identity_provider_link(
        self,
        user_id: int,
        idp_id: int,
    ) -> None:
        """Unlink an IdP from a user as an administrator (no step-up)."""
        auth_identity_link_service.admin_delete_identity_provider_link(
            user_id,
            idp_id,
            self._db,
        )

    def validate_and_claim_browser_link_token(
        self,
        link_token: str,
        idp_id: int,
        client_ip: str | None,
    ) -> int:
        """Validate, IP-check, and atomically claim a browser-redirect link token."""
        return auth_identity_link_service.validate_and_claim_browser_link_token(
            link_token,
            idp_id,
            client_ip,
            self._db,
        )

    def get_identity_link_counts_for_users(self, user_ids: list[int]) -> dict[int, int]:
        """Return identity-link count per user ID in a single grouped query."""
        return auth_identity_link_service.get_identity_link_counts_for_users(user_ids, self._db)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_identity_service(
    db: Annotated[Session, Depends(core_database.get_db)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
) -> IdentityService:
    """FastAPI dependency that yields a per-request IdentityService.

    A new :class:`DefaultIdentityService` is constructed for every
    request.  Never use a module-level singleton.

    The resolved :class:`~auth.principal.Principal` should be cached
    on ``request.state.principal`` by the caller so that downstream
    dependencies within the same request do not trigger extra database
    lookups.

    Args:
        db: SQLAlchemy database session (from ``get_db``).
        token_manager: JWT token manager.
        password_hasher: Argon2/bcrypt password hasher.

    Returns:
        IdentityService: A fresh ``DefaultIdentityService`` instance
            bound to this request's dependencies.
    """
    return DefaultIdentityService(db, token_manager, password_hasher)
