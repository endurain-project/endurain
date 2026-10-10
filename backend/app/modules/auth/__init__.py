"""Authentication package.

Provides the FastAPI router, JWT token issuance and validation,
password hashing, scope enforcement, API-key validation, and the
progressive-lockout stores used during login and MFA verification.

Persistence-bearing concerns (identity providers, IdP link tokens,
MFA backup codes, OAuth state) live in dedicated sub-packages and
expose their own models, schemas, and CRUD modules.

Exports:
    - Password hashing: ``PasswordHasher``, ``PasswordPolicyError``,
      ``get_password_hasher``
    - JWT: ``TokenManager``, ``TokenType``, ``get_token_manager``
    - Security dependencies: ``AuthContext``, ``oauth2_scheme``,
      ``validate_access_token_expiration``, ``validate_refresh_token``,
      ``check_auth_scopes``,
      ``get_sub_from_access_token``, ``get_sid_from_access_token``,
      ``get_sub_from_refresh_token``, ``get_sid_from_refresh_token``,
      ``validate_access_token_or_api_key``,
      ``header_client_type_scheme``, ``header_csrf_token_scheme``

      Scope enforcement (``check_scopes``) is provided by
      :mod:`modules.auth.dependencies`, which resolves the full principal.
    - Schemas: ``LoginRequest``, ``MFALoginRequest``,
      ``MFARequiredResponse``, ``MobileSessionResponse``,
      ``TokenResponseWeb``, ``TokenResponseMobile``,
      ``LogoutResponse``
    - Stores: ``PendingMFALogin``, ``FailedLoginAttempts``,
      ``StepUpAttempts``, ``get_pending_mfa_store``,
      ``get_failed_login_attempts``, ``get_step_up_attempts``,
      ``cleanup_expired_pending_mfa_logins``,
      ``clear_pending_mfa_for_user``
    - Helpers: ``authenticate_user``, ``complete_login``,
      ``create_tokens``, ``create_mobile_pkce_session_response``
"""

# Ensure the auth-owned credential ORM model is registered with SQLAlchemy's
# mapper registry whenever the auth package loads, so the
# ``Users.local_credential`` relationship resolves at mapper configuration time.
from . import credentials  # noqa: F401
from ._internal.internal_dependencies import (
    AuthContext,
    get_sid_from_access_token,
    get_sid_from_refresh_token,
    get_sub_from_access_token,
    get_sub_from_refresh_token,
    header_client_type_scheme,
    header_csrf_token_scheme,
    oauth2_scheme,
    validate_access_token_expiration,
    validate_access_token_or_api_key,
    validate_refresh_token,
)
from ._internal.password_hasher import (
    PasswordHasher,
    PasswordPolicyError,
    get_password_hasher,
)
from ._internal.security_stores import (
    FailedLoginAttempts,
    PendingMFALogin,
    StepUpAttempts,
    StepUpStore,
    cleanup_expired_pending_mfa_logins,
    clear_pending_mfa_for_user,
    get_failed_login_attempts,
    get_pending_mfa_store,
    get_step_up_attempts,
)
from ._internal.token_manager import TokenManager, TokenType, get_token_manager
from .dependencies import check_auth_scopes
from .schema import (
    LoginRequest,
    LogoutResponse,
    MFALoginRequest,
    MFARequiredResponse,
    MobileSessionResponse,
    TokenResponseMobile,
    TokenResponseWeb,
)
from .utils import (
    authenticate_user,
    complete_login,
    create_mobile_pkce_session_response,
    create_tokens,
)

__all__ = [
    # Security dependencies
    "AuthContext",
    "FailedLoginAttempts",
    # Schemas
    "LoginRequest",
    "LogoutResponse",
    "MFALoginRequest",
    "MFARequiredResponse",
    "MobileSessionResponse",
    # Password hashing
    "PasswordHasher",
    "PasswordPolicyError",
    # Auth security stores / lockout
    "PendingMFALogin",
    "StepUpAttempts",
    "StepUpStore",
    # JWT / token management
    "TokenManager",
    "TokenResponseMobile",
    "TokenResponseWeb",
    "TokenType",
    # Helpers
    "authenticate_user",
    "check_auth_scopes",
    "cleanup_expired_pending_mfa_logins",
    "clear_pending_mfa_for_user",
    "complete_login",
    "create_mobile_pkce_session_response",
    "create_tokens",
    "get_failed_login_attempts",
    "get_password_hasher",
    "get_pending_mfa_store",
    "get_sid_from_access_token",
    "get_sid_from_refresh_token",
    "get_step_up_attempts",
    "get_sub_from_access_token",
    "get_sub_from_refresh_token",
    "get_token_manager",
    "header_client_type_scheme",
    "header_csrf_token_scheme",
    "oauth2_scheme",
    "validate_access_token_expiration",
    "validate_access_token_or_api_key",
    "validate_refresh_token",
]
