"""Public authentication dependencies for routers and application modules."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

import jasil.audit as jasil_audit
from fastapi import Depends, Path, Query, Request
from fastapi.security import APIKeyHeader, SecurityScopes
from sqlalchemy.orm import Session

import core.config as core_config
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import core.request_context as core_request_context
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.authentication.audit_actions as authentication_audit_actions
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.constants as auth_constants
import modules.auth.contracts as auth_contracts
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.dependencies as identity_providers_dependencies
import modules.auth.mfa.dependencies as auth_mfa_dependencies
import modules.auth.schema as auth_schema
import modules.auth.sessions.contracts as sessions_contracts

logger = core_logger.get_logger(__name__)

get_bearer_token = authentication_dependencies.get_bearer_token
header_api_key_scheme = APIKeyHeader(name="X-API-Key", scheme_name="ApiKey", auto_error=False)
AuthContext = auth_contracts.AuthContext
ApiKeyId = Annotated[str, Path(min_length=1)]
IdentityProviderSlug = Annotated[str, Path(min_length=1)]
AuthSessionId = Annotated[str, Path(min_length=1)]
set_idp_browser_binding_cookie = identity_providers_dependencies.set_browser_binding_cookie


def get_access_token(
    access_token: Annotated[str | None, Depends(get_bearer_token)],
) -> str:
    """Require an access token from the Authorization header."""
    if access_token is None:
        raise core_exceptions.InvalidTokenError("Access token missing from Authorization header", scheme="Bearer")
    return access_token


def _require_scopes(granted: Iterable[str], required: SecurityScopes) -> None:
    """Refuse a caller that lacks any scope the route declares.

    Args:
        granted: Scopes the caller holds.
        required: Scopes the route requires.

    Raises:
        PermissionDeniedError: When a required scope is missing.
    """
    missing = set(required.scopes) - set(granted)
    if missing:
        logger.warning("Request refused: missing scopes <scopes>", extra=core_logger.context(scopes=sorted(missing)))
        jasil_audit.record_detached(
            authentication_audit_actions.SCOPE_DENIED,
            outcome=jasil_audit.Outcome.DENIED,
            details=authentication_audit_actions.ScopeDeniedDetails(missing_scopes=sorted(missing)),
        )
        error = core_exceptions.PermissionDeniedError(f"Missing permissions: {', '.join(sorted(missing))}")
        error.headers = {"WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{" ".join(required.scopes)}"'}
        error.extensions = {"missing_scopes": sorted(missing)}
        raise error


def _matches_template(template: list[str], segments: list[str]) -> bool:
    """Tell whether a path's segments fit a route template's, a ``{...}`` segment fitting any non-empty one."""
    return len(template) == len(segments) and all(
        wanted == actual or (wanted.startswith("{") and bool(actual))
        for wanted, actual in zip(template, segments, strict=True)
    )


def _is_mfa_enrolment_request(request: Request) -> bool:
    """Tell whether a request is one an account that must enrol MFA may make.

    The request is matched on its method and path, not on the matched route, whose template does not carry the
    prefix its router is included under. A ``{...}`` segment of a template matches any one segment.

    Args:
        request: The request.

    Returns:
        True when the request is one of ``auth_constants.MFA_ENROLMENT_ROUTES``.
    """
    root_path = request.scope.get("root_path", "")
    path = request.scope["path"].removeprefix(root_path).removeprefix(core_config.ROOT_PATH)
    segments = path.split("/")
    return any(
        method == request.method and _matches_template(template.split("/"), segments)
        for method, template in auth_constants.MFA_ENROLMENT_ROUTES
    )


def _require_mfa_enrolment_exempt(principal: auth_contracts.Principal, request: Request) -> None:
    """Refuse a request from an account that must enrol MFA, unless enrolment needs it.

    Every authenticated request passes here, so the refusal is stated once rather than per route.

    Args:
        principal: The resolved caller.
        request: The request, whose method and path say what it is for.

    Raises:
        MfaEnrolmentRequiredError: When the server requires MFA of the account, it has none and the request is not
            one enrolment needs.
    """
    if not principal.mfa_enrolment_required or _is_mfa_enrolment_request(request):
        return
    logger.warning(
        "Request refused: user <user_id> must enrol MFA", extra=core_logger.context(user_id=principal.user_id)
    )
    raise core_exceptions.MfaEnrolmentRequiredError()


def _resolve_and_cache_principal(access_token: str, request: Request, db: Session) -> auth_contracts.Principal:
    """Resolve the request principal once and cache it on request state, and refuse it while it must enrol MFA."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        principal = authentication_integration.resolve_from_access_token(access_token, db)
        request.state.principal = principal
    _require_mfa_enrolment_exempt(principal, request)
    return principal


def validate_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> None:
    """Resolve an access token and require an active user."""
    _resolve_and_cache_principal(access_token, request, db)


def require_scopes(granted: Iterable[str], *scopes: str) -> None:
    """Refuse a caller that lacks any of the given scopes, with the same 403 a route's scope check sends.

    For a handler that needs a scope only on some inputs, after its route-level check passed.

    Args:
        granted: Scopes the caller holds.
        *scopes: Scopes the input requires.

    Raises:
        PermissionDeniedError: When a required scope is missing.
    """
    _require_scopes(granted, SecurityScopes(scopes=list(scopes)))


def check_scopes(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
    security_scopes: SecurityScopes,
) -> None:
    """Resolve an access token and require all declared scopes."""
    principal = _resolve_and_cache_principal(access_token, request, db)
    _require_scopes(principal.scopes, security_scopes)


def get_sub_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> int:
    """Return the authenticated user's id after resolving the access token."""
    return _resolve_and_cache_principal(access_token, request, db).user_id


def get_scopes_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> frozenset[str]:
    """Return the scopes granted to the authenticated caller."""
    return _resolve_and_cache_principal(access_token, request, db).scopes


def get_sid_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> str:
    """Return the session id carried by a validated access token."""
    principal = _resolve_and_cache_principal(access_token, request, db)
    if not isinstance(principal.credential, auth_contracts.AccessTokenCred):
        raise core_exceptions.UnauthenticatedError("Invalid credential type for session ID")
    return principal.credential.session_id


def validate_access_token_or_api_key(
    request: Request,
    db: core_dependencies.DbSession,
    access_token: str | None = Depends(get_bearer_token),
    api_key_header: str | None = Depends(header_api_key_scheme),
    api_key_query: str | None = Query(None, alias="api_key", include_in_schema=False),
) -> AuthContext:
    """Resolve a JWT or API key, preserving request-level principal caching."""
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        _require_mfa_enrolment_exempt(cached, request)
        return AuthContext(cached.user_id, list(cached.scopes), "api_key" if cached.is_api_key() else "jwt")
    if access_token is not None:
        principal = authentication_integration.resolve_from_access_token(access_token, db)
        auth_type = "jwt"
    else:
        raw_key = api_key_header
        if raw_key is None and api_key_query is not None and core_config.settings.ALLOW_API_KEY_QUERY_PARAM:
            logger.warning(
                "API key supplied via query string (?api_key=). "
                "This is a security risk: credentials appear in access logs and browser history. "
                "Set X-API-Key header instead."
            )
            raw_key = api_key_query
        if raw_key is None:
            raise core_exceptions.InvalidTokenError(
                "Not authenticated. Provide a Bearer token or an API key.", scheme="Bearer"
            )
        principal = authentication_integration.resolve_from_api_key(raw_key, request, db)
        auth_type = "api_key"
    request.state.principal = principal
    _require_mfa_enrolment_exempt(principal, request)
    return AuthContext(principal.user_id, list(principal.scopes), auth_type)


def get_user_id_from_auth(
    auth: Annotated[AuthContext, Depends(validate_access_token_or_api_key)],
) -> int:
    """Return the user id from resolved JWT or API-key authentication."""
    return auth.user_id


def check_auth_scopes(
    auth: Annotated[AuthContext, Depends(validate_access_token_or_api_key)],
    security_scopes: SecurityScopes,
) -> None:
    """Require all declared scopes from a JWT or API-key context."""
    _require_scopes(auth.scopes, security_scopes)


def audit_context_from_request() -> jasil_audit.AuditContext:
    """Describe who is acting, for the audit trail.

    Installed by the composition root as the audit context provider, so it is read when a row is written. Inside
    an HTTP request the actor is the principal an auth dependency cached on the request (anonymous until one has),
    with the client's address and user agent. Outside one the work is the system's own: a scheduled job, a
    durable-job handler or startup.

    Returns:
        The context for the row being written.
    """
    request = core_request_context.get_current_request()
    if request is None:
        return jasil_audit.AuditContext(actor_type=jasil_audit.ActorType.SYSTEM, source=jasil_audit.Source.WORKER)
    ip_address = core_network.get_ip_address(request)
    client_ip = None if ip_address == "unknown" else ip_address
    user_agent = core_network.get_user_agent(request) or None
    principal: auth_contracts.Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        return jasil_audit.AuditContext(ip_address=client_ip, user_agent=user_agent)
    credential_id = principal.credential_id()
    return jasil_audit.AuditContext(
        actor_type=jasil_audit.ActorType.API_KEY if principal.is_api_key() else jasil_audit.ActorType.USER,
        actor_id=str(principal.user_id),
        credential_type=principal.credential_type(),
        credential_id=None if credential_id is None else str(credential_id),
        ip_address=client_ip,
        user_agent=user_agent,
    )


#: Authenticated user id extracted from a resolved access token.
CurrentUserId = Annotated[int, Depends(get_sub_from_access_token)]
#: Scopes granted to the authenticated caller.
CurrentScopes = Annotated[frozenset[str], Depends(get_scopes_from_access_token)]
#: Session id carried by a resolved access token.
CurrentSessionId = Annotated[str, Depends(get_sid_from_access_token)]
StepUpStore = account_security_integration.StepUpStore
get_step_up_attempts = account_security_integration.get_step_up_attempts
MFASecretStoreBackend = auth_mfa_dependencies.MFASecretStoreBackend
get_mfa_secret_store = auth_mfa_dependencies.get_mfa_secret_store


def get_step_up_verifier(
    user_id: CurrentUserId,
    session_id: CurrentSessionId,
    step_up_store: Annotated[StepUpStore, Depends(get_step_up_attempts)],
    db: core_dependencies.DbSession,
) -> identity_providers_contracts.StepUpVerifier:
    """Return the step-up verifier bound to the calling administrator.

    The identity-provider package declares the verifier it needs and cannot import ``account_security``, which
    depends on it; this installs the ``account_security`` implementation, with the administrator's own id and
    session.

    Args:
        user_id: The authenticated administrator.
        session_id: The administrator's session.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        A verifier that refuses by raising, as ``account_security_integration.verify_step_up`` does.
    """

    def verify(step_up: auth_schema.StepUpVerification, action: identity_providers_constants.StepUpAction) -> None:
        account_security_integration.verify_step_up(step_up, user_id, session_id, action, step_up_store, db)

    return verify


#: Verifies the calling administrator's step-up for an operation the identity-provider package administers.
StepUpVerifierDep = Annotated[identity_providers_contracts.StepUpVerifier, Depends(get_step_up_verifier)]


def get_session_revoke_verifier(verify_step_up: StepUpVerifierDep) -> sessions_contracts.SessionRevokeVerifier:
    """Return the step-up verifier for an administrator ending another user's sessions.

    The sessions package cannot name the step-up action (it lives in ``identity_providers``, which depends on
    it), so the action is bound here.

    Args:
        verify_step_up: The verifier bound to the calling administrator.

    Returns:
        A verifier that checks the step-up for the session-revoke action and refuses by raising.
    """

    def verify(step_up: auth_schema.StepUpVerification) -> None:
        verify_step_up(step_up, identity_providers_constants.StepUpAction.ADMIN_SESSIONS_REVOKE)

    return verify


#: Verifies the calling administrator's step-up for ending another user's sessions.
SessionRevokeVerifierDep = Annotated[sessions_contracts.SessionRevokeVerifier, Depends(get_session_revoke_verifier)]

__all__ = [
    "AuthContext",
    "CurrentScopes",
    "CurrentSessionId",
    "CurrentUserId",
    "MFASecretStoreBackend",
    "SessionRevokeVerifierDep",
    "StepUpStore",
    "StepUpVerifierDep",
    "audit_context_from_request",
    "check_auth_scopes",
    "check_scopes",
    "get_access_token",
    "get_mfa_secret_store",
    "get_scopes_from_access_token",
    "get_session_revoke_verifier",
    "get_sid_from_access_token",
    "get_step_up_attempts",
    "get_step_up_verifier",
    "get_sub_from_access_token",
    "get_user_id_from_auth",
    "require_scopes",
    "validate_access_token",
    "validate_access_token_or_api_key",
]
