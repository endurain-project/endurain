"""Public authentication dependencies for routers and application modules."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

import jasil.audit as jasil_audit
from fastapi import Depends, Path, Request
from fastapi.security import APIKeyHeader, SecurityScopes
from jasil.providers import StateBackendUnavailableError, StateProvider
from sqlalchemy.orm import Session

import core.config as core_config
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.hashing as core_hashing
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

#: How long a credential's MFA-enrolment refusal is audited once.
_MFA_ENROLMENT_AUDIT_WINDOW_SECONDS = 24 * 60 * 60

get_bearer_token = authentication_dependencies.get_bearer_token
header_api_key_scheme = APIKeyHeader(name="X-API-Key", scheme_name="ApiKey", auto_error=False)
ApiKeyId = Annotated[str, Path(min_length=1)]
IdentityProviderSlug = Annotated[str, Path(min_length=1)]
AuthSessionId = Annotated[str, Path(min_length=1)]
set_idp_browser_binding_cookie = identity_providers_dependencies.set_browser_binding_cookie


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


def _claim_mfa_enrolment_audit(principal: auth_contracts.Principal, state: StateProvider) -> bool:
    """Claim the day's audit row for a credential's MFA-enrolment refusals, so a retrying client writes one.

    The claim is keyed by a hash of the credential's id, so no session id or key id reaches the state store. When
    the store cannot be reached the row is written, since an audit row must not be lost to a retry guard.

    Args:
        principal: The refused caller.
        state: The platform state provider.

    Returns:
        True when the refusal is to be audited, False when the credential was audited within the day.
    """
    key = f"endurain:auth:mfa_enrolment_denied:{core_hashing.sha256_hex(str(principal.credential_id()))}"
    try:
        return state.set_if_absent(key, b"1", _MFA_ENROLMENT_AUDIT_WINDOW_SECONDS)
    except StateBackendUnavailableError as err:
        logger.error("MFA-enrolment refusal audit guard unavailable", exc_info=err)
        return True


def _require_mfa_enrolment_exempt(principal: auth_contracts.Principal, request: Request, state: StateProvider) -> None:
    """Refuse a request from an account that must enrol MFA, unless enrolment needs it.

    Every authenticated request passes here, so the refusal is stated once rather than per route. It is audited
    at most once per credential per day.

    Args:
        principal: The resolved caller.
        request: The request, whose method and path say what it is for.
        state: The platform state provider.

    Raises:
        MfaEnrolmentRequiredError: When the server requires MFA of the account, it has none and the request is not
            one enrolment needs.
    """
    if not principal.mfa_enrolment_required or _is_mfa_enrolment_request(request):
        return
    logger.warning(
        "Request refused: user <user_id> must enrol MFA", extra=core_logger.context(user_id=principal.user_id)
    )
    if _claim_mfa_enrolment_audit(principal, state):
        jasil_audit.record_detached(
            authentication_audit_actions.MFA_ENROLMENT_DENIED,
            outcome=jasil_audit.Outcome.DENIED,
            details=authentication_audit_actions.MfaEnrolmentDeniedDetails(credential_type=principal.credential_type()),
        )
    raise core_exceptions.MfaEnrolmentRequiredError()


def _resolve_principal(
    request: Request,
    db: Session,
    access_token: str | None,
    api_key_header: str | None,
) -> auth_contracts.Principal:
    """Resolve the access token, or else the API key, a request carries.

    The ``?api_key=`` query parameter is read from the request rather than declared, so it is not a parameter of
    every operation: it is used only when the server allows it and no header is sent.

    Args:
        request: The request.
        db: Database session.
        access_token: The ``Authorization: Bearer`` token, if any. It wins over an API key.
        api_key_header: The ``X-API-Key`` header, if any.

    Returns:
        The caller.

    Raises:
        InvalidTokenError: When the request carries no credential.
    """
    if access_token is not None:
        return authentication_integration.resolve_from_access_token(access_token, db)
    raw_key = api_key_header
    api_key_query = request.query_params.get("api_key")
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
    return authentication_integration.resolve_from_api_key(raw_key, request, db)


def get_principal(
    request: Request,
    db: core_dependencies.DbSession,
    access_token: Annotated[str | None, Depends(get_bearer_token)],
    api_key_header: Annotated[str | None, Depends(header_api_key_scheme)],
    state: core_dependencies.PlatformState,
) -> auth_contracts.Principal:
    """Resolve the caller's access token or API key once per request, and refuse it while it must enrol MFA.

    Every authenticated route reaches its caller through here, so an API key is accepted wherever its scopes
    are: a route's scope check is the only thing that decides what a key reaches.

    Args:
        request: The request; the resolved caller is cached on its state for the audit trail.
        db: Database session.
        access_token: The ``Authorization: Bearer`` token, if any.
        api_key_header: The ``X-API-Key`` header, if any.
        state: The platform state provider.

    Returns:
        The caller.
    """
    principal = getattr(request.state, "principal", None)
    if principal is None:
        principal = _resolve_principal(request, db, access_token, api_key_header)
        request.state.principal = principal
    _require_mfa_enrolment_exempt(principal, request, state)
    return principal


#: The resolved caller: a signed-in session's access token or an API key.
CurrentPrincipal = Annotated[auth_contracts.Principal, Depends(get_principal)]


def authenticate(principal: CurrentPrincipal) -> None:
    """Require an authenticated caller, by access token or API key."""


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


def check_scopes(principal: CurrentPrincipal, security_scopes: SecurityScopes) -> None:
    """Require every scope the route declares of the caller."""
    _require_scopes(principal.scopes, security_scopes)


def get_current_user_id(principal: CurrentPrincipal) -> int:
    """Return the authenticated user's id."""
    return principal.user_id


def get_current_scopes(principal: CurrentPrincipal) -> frozenset[str]:
    """Return the scopes granted to the authenticated caller."""
    return principal.scopes


def get_sid_from_access_token(principal: CurrentPrincipal) -> str:
    """Return the session id carried by the caller's access token.

    Args:
        principal: The caller.

    Returns:
        The session id.

    Raises:
        PermissionDeniedError: When the caller is an API key, which has no session: the route acts for a signed-in
            session (a step-up, a WebSocket ticket bound to the session), not for a key.
    """
    if not isinstance(principal.credential, auth_contracts.AccessTokenCred):
        logger.warning(
            "Request refused: user <user_id> called a session-only route with an API key",
            extra=core_logger.context(user_id=principal.user_id),
        )
        raise core_exceptions.PermissionDeniedError("This operation needs a signed-in session; an API key cannot do it")
    return principal.credential.session_id


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


#: Authenticated user id, by access token or API key.
CurrentUserId = Annotated[int, Depends(get_current_user_id)]
#: Scopes granted to the authenticated caller.
CurrentScopes = Annotated[frozenset[str], Depends(get_current_scopes)]
#: Session id carried by the caller's access token; an API key is refused.
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
    "CurrentPrincipal",
    "CurrentScopes",
    "CurrentSessionId",
    "CurrentUserId",
    "MFASecretStoreBackend",
    "SessionRevokeVerifierDep",
    "StepUpStore",
    "StepUpVerifierDep",
    "audit_context_from_request",
    "authenticate",
    "check_scopes",
    "get_current_scopes",
    "get_current_user_id",
    "get_mfa_secret_store",
    "get_principal",
    "get_session_revoke_verifier",
    "get_sid_from_access_token",
    "get_step_up_attempts",
    "get_step_up_verifier",
    "require_scopes",
]
