"""COROS OAuth 2.0 discovery, dynamic registration and token operations.

COROS publishes a standard authorization-server document from the MCP gateway.
Endurain registers a public client dynamically (PKCE, no secret required) and
uses the authorization-code flow with ``openid offline_access mcp.tools``.
"""

import base64
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx2

import core.logger as core_logger
import modules.coros.constants as coros_constants
import modules.coros.contracts as coros_contracts

logger = core_logger.get_logger(__name__)

_HTTP_TIMEOUT_SECONDS = 20.0
_COROS_HOST_SUFFIX = ".coros.com"
_COROS_APEX = "coros.com"


class CorosOAuthError(Exception):
    """Base error for a failed COROS OAuth operation."""


class CorosAuthenticationError(CorosOAuthError):
    """The user must reconnect: a grant was rejected or expired."""


class CorosTransientError(CorosOAuthError):
    """A network, timeout or server-side failure that can be retried."""


class CorosProtocolError(CorosOAuthError):
    """COROS returned a response this integration cannot interpret."""


def generate_state() -> str:
    """Return an unguessable OAuth state value."""
    return secrets.token_urlsafe(32)


def generate_pkce_pair() -> tuple[str, str]:
    """Return a PKCE verifier and its S256 challenge.

    Returns:
        The verifier and the base64url-encoded SHA-256 challenge.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _is_coros_url(value: str) -> bool:
    """Return whether a URL is HTTPS on the COROS domain.

    Args:
        value: URL to check.

    Returns:
        True when the URL can be used for a COROS OAuth round-trip.
    """
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and (host == _COROS_APEX or host.endswith(_COROS_HOST_SUFFIX))
        and not parsed.username
        and not parsed.password
    )


def _client(client: httpx2.Client | None) -> httpx2.Client:
    """Return the supplied HTTP client or a short-lived default one."""
    return client or httpx2.Client(timeout=_HTTP_TIMEOUT_SECONDS, follow_redirects=True)


def _get_json(client: httpx2.Client, url: str) -> dict[str, Any]:
    """GET a JSON document and map transport failures to domain errors.

    Args:
        client: HTTP client.
        url: Document URL.

    Returns:
        The decoded JSON object.

    Raises:
        CorosTransientError: On network, timeout or 5xx failures.
        CorosProtocolError: On a non-200 response or a non-object payload.
    """
    try:
        response = client.get(url)
    except (httpx2.TimeoutException, httpx2.RequestError) as err:
        raise CorosTransientError("COROS OAuth discovery failed") from err
    if response.status_code >= 500:
        raise CorosTransientError("COROS OAuth discovery is unavailable")
    if response.status_code != 200:
        raise CorosProtocolError("COROS OAuth metadata was not available")
    try:
        payload = response.json()
    except ValueError as err:
        raise CorosProtocolError("COROS OAuth metadata was not JSON") from err
    if not isinstance(payload, dict):
        raise CorosProtocolError("COROS OAuth metadata was not an object")
    return payload


def _resource_metadata_url(www_authenticate: str) -> str | None:
    """Extract ``resource_metadata`` from a ``WWW-Authenticate`` header.

    Args:
        www_authenticate: Header value.

    Returns:
        The metadata URL, or None when the header does not carry one.
    """
    match = re.search(r'resource_metadata\s*=\s*"?([^",\s]+)"?', www_authenticate, re.IGNORECASE)
    return match.group(1) if match else None


def discover_metadata(client: httpx2.Client | None = None) -> coros_contracts.CorosOAuthMetadata:
    """Discover the COROS authorization-server metadata.

    The gateway publishes an OIDC document on the global MCP host. When that is
    unavailable, the protected-resource metadata advertised by the MCP
    endpoint's ``401`` response is used as the fallback.

    Args:
        client: Optional HTTP client, for tests.

    Returns:
        The discovered metadata.

    Raises:
        CorosTransientError: When COROS cannot be reached.
        CorosProtocolError: When the metadata is missing required endpoints.
    """
    http = _client(client)
    try:
        origin = urlparse(coros_constants.MCP_URL)
        discovery_url = f"{origin.scheme}://{origin.netloc}/.well-known/openid-configuration"
        try:
            payload = _get_json(http, discovery_url)
        except CorosProtocolError:
            return _discover_from_protected_resource(http)
        metadata = _metadata_from_oidc(payload, http)
        if metadata is not None:
            return metadata

        return _discover_from_protected_resource(http)
    finally:
        if client is None:
            http.close()


def _metadata_from_oidc(payload: dict[str, Any], client: httpx2.Client) -> coros_contracts.CorosOAuthMetadata | None:
    """Build metadata from an OIDC document, falling back to resource metadata.

    Args:
        payload: OIDC discovery document.
        client: HTTP client used for the protected-resource fallback.

    Returns:
        The metadata, or None when the document is not usable.
    """
    issuer = payload.get("issuer")
    if not isinstance(issuer, str) or not _is_coros_url(issuer):
        return None
    mcp_url = f"{issuer.rstrip('/')}/mcp"
    try:
        protected = _get_json(client, f"{issuer.rstrip('/')}/.well-known/oauth-protected-resource/mcp")
        resource = protected.get("resource")
        if isinstance(resource, str) and _is_coros_url(resource):
            mcp_url = resource
    except (CorosOAuthError, ValueError):
        pass
    return _build_metadata(payload, mcp_url)


def _discover_from_protected_resource(
    client: httpx2.Client,
) -> coros_contracts.CorosOAuthMetadata:
    """Discover metadata through the MCP endpoint's ``401`` challenge.

    Args:
        client: HTTP client.

    Returns:
        The discovered metadata.

    Raises:
        CorosProtocolError: When the endpoint does not advertise usable metadata.
    """
    try:
        response = client.get(coros_constants.MCP_URL)
    except (httpx2.TimeoutException, httpx2.RequestError) as err:
        raise CorosTransientError("COROS MCP discovery failed") from err
    metadata_url = _resource_metadata_url(response.headers.get("www-authenticate", ""))
    if not metadata_url or not _is_coros_url(metadata_url):
        raise CorosProtocolError("COROS did not advertise OAuth metadata")
    protected = _get_json(client, metadata_url)
    servers = protected.get("authorization_servers")
    if not isinstance(servers, list) or not servers or not isinstance(servers[0], str):
        raise CorosProtocolError("COROS did not advertise an authorization server")
    issuer = servers[0].rstrip("/")
    if not _is_coros_url(issuer):
        raise CorosProtocolError("COROS advertised an untrusted authorization server")
    payload = _get_json(client, f"{issuer}/.well-known/oauth-authorization-server")
    resource = protected.get("resource")
    mcp_url = resource if isinstance(resource, str) and _is_coros_url(resource) else f"{issuer}/mcp"
    return _build_metadata(payload, mcp_url)


def _build_metadata(payload: dict[str, Any], mcp_url: str) -> coros_contracts.CorosOAuthMetadata:
    """Validate an authorization-server document and build the contract.

    Args:
        payload: Authorization-server metadata.
        mcp_url: Protected MCP resource.

    Returns:
        The metadata contract.

    Raises:
        CorosProtocolError: When a required endpoint is missing or untrusted.
    """
    required = ("issuer", "authorization_endpoint", "token_endpoint")
    for key in required:
        value = payload.get(key)
        if not isinstance(value, str) or not _is_coros_url(value):
            raise CorosProtocolError(f"COROS OAuth metadata is missing a trusted {key}")
    scopes = payload.get("scopes_supported")
    published_scopes = tuple(scope for scope in scopes if isinstance(scope, str)) if isinstance(scopes, list) else ()
    selected_scopes = published_scopes or coros_constants.SCOPES
    if not set(coros_constants.SCOPES).issubset(selected_scopes):
        raise CorosProtocolError("COROS does not publish the required OAuth scopes")
    revocation = payload.get("revocation_endpoint")
    registration = payload.get("registration_endpoint")
    return coros_contracts.CorosOAuthMetadata(
        issuer=str(payload["issuer"]).rstrip("/"),
        authorization_endpoint=str(payload["authorization_endpoint"]),
        token_endpoint=str(payload["token_endpoint"]),
        revocation_endpoint=str(revocation) if isinstance(revocation, str) and _is_coros_url(revocation) else None,
        registration_endpoint=(
            str(registration) if isinstance(registration, str) and _is_coros_url(registration) else None
        ),
        mcp_url=mcp_url,
        scopes=selected_scopes,
    )


def register_client(
    metadata: coros_contracts.CorosOAuthMetadata,
    redirect_uri: str,
    *,
    client_name: str = "Endurain",
    client: httpx2.Client | None = None,
) -> coros_contracts.CorosClientRegistration:
    """Register a public OAuth client for this callback URI.

    Args:
        metadata: Discovered authorization-server metadata.
        redirect_uri: Callback URI COROS will redirect to.
        client_name: Display name registered with COROS.
        client: Optional HTTP client, for tests.

    Returns:
        The registered client.

    Raises:
        CorosTransientError: When COROS cannot be reached.
        CorosProtocolError: When registration is rejected or malformed.
    """
    if metadata.registration_endpoint is None:
        raise CorosProtocolError("COROS does not advertise dynamic client registration")
    http = _client(client)
    try:
        response = http.post(
            metadata.registration_endpoint,
            json={
                "client_name": client_name,
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": " ".join(metadata.scopes),
                "token_endpoint_auth_method": "none",
            },
        )
    except (httpx2.TimeoutException, httpx2.RequestError) as err:
        raise CorosTransientError("COROS client registration failed") from err
    finally:
        if client is None:
            http.close()
    if response.status_code == 429 or response.status_code >= 500:
        raise CorosTransientError("COROS client registration is unavailable")
    if response.status_code not in (200, 201):
        raise CorosProtocolError("COROS rejected client registration")
    try:
        payload = response.json()
    except ValueError as err:
        raise CorosProtocolError("COROS client registration was not JSON") from err
    client_id = payload.get("client_id") if isinstance(payload, dict) else None
    if not isinstance(client_id, str) or not client_id:
        raise CorosProtocolError("COROS client registration returned no client id")
    secret = payload.get("client_secret")
    return coros_contracts.CorosClientRegistration(
        client_id=client_id,
        client_secret=secret if isinstance(secret, str) and secret else None,
    )


def build_authorization_url(
    metadata: coros_contracts.CorosOAuthMetadata,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    """Build the browser authorization URL.

    Args:
        metadata: Discovered authorization-server metadata.
        client_id: Registered client id.
        redirect_uri: Registered callback URI.
        state: CSRF state.
        code_challenge: PKCE S256 challenge.

    Returns:
        The absolute authorization URL.
    """
    from urllib.parse import urlencode

    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(metadata.scopes),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "resource": metadata.mcp_url,
            "state": state,
        }
    )
    return f"{metadata.authorization_endpoint}?{query}"


def _post_token(
    metadata: coros_contracts.CorosOAuthMetadata,
    data: dict[str, str],
    client: httpx2.Client | None,
) -> dict[str, Any]:
    """POST a token-endpoint form and return its JSON payload.

    Args:
        metadata: Discovered metadata.
        data: Form fields.
        client: Optional HTTP client.

    Returns:
        The decoded response object.

    Raises:
        CorosTransientError: On network or server failures.
        CorosAuthenticationError: On a rejected grant or client.
        CorosProtocolError: On any other rejected request.
    """
    http = _client(client)
    try:
        response = http.post(metadata.token_endpoint, data=data)
    except (httpx2.TimeoutException, httpx2.RequestError) as err:
        raise CorosTransientError("COROS token endpoint is unavailable") from err
    finally:
        if client is None:
            http.close()
    if response.status_code == 429 or response.status_code >= 500:
        raise CorosTransientError("COROS token endpoint is unavailable")
    try:
        payload = response.json()
    except ValueError as err:
        raise CorosProtocolError("COROS token endpoint returned invalid JSON") from err
    if response.status_code != 200:
        error = payload.get("error") if isinstance(payload, dict) else None
        if error in {"invalid_grant", "invalid_client", "unauthorized_client"}:
            raise CorosAuthenticationError("COROS rejected the OAuth grant")
        raise CorosProtocolError("COROS token request failed")
    if not isinstance(payload, dict):
        raise CorosProtocolError("COROS token response was not an object")
    return payload


def _token_set(
    payload: dict[str, Any],
    *,
    fallback_refresh_token: str | None = None,
) -> coros_contracts.CorosTokenSet:
    """Turn a token-endpoint payload into the token contract.

    Args:
        payload: Token-endpoint response.
        fallback_refresh_token: Refresh token to retain when COROS omits a new one.

    Returns:
        The token set.

    Raises:
        CorosProtocolError: When no usable access/refresh token is returned.
    """
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token") or fallback_refresh_token
    if not isinstance(access_token, str) or not access_token:
        raise CorosProtocolError("COROS token response has no access token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise CorosProtocolError("COROS token response has no refresh token")
    now = datetime.now(UTC)
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, str) and expires_in.isdigit():
        expires_in = int(expires_in)
    access_seconds = (
        int(expires_in)
        if isinstance(expires_in, int | float) and expires_in > 0
        else coros_constants.ACCESS_TOKEN_FALLBACK_DAYS * 86400
    )
    refresh_expires_in = payload.get("refresh_token_expires_in", payload.get("refresh_expires_in"))
    if isinstance(refresh_expires_in, str) and refresh_expires_in.isdigit():
        refresh_expires_in = int(refresh_expires_in)
    refresh_seconds = (
        int(refresh_expires_in)
        if isinstance(refresh_expires_in, int | float) and refresh_expires_in > 0
        else coros_constants.REFRESH_TOKEN_FALLBACK_DAYS * 86400
    )
    scope = payload.get("scope")
    return coros_contracts.CorosTokenSet(
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=now + timedelta(seconds=access_seconds),
        refresh_token_expires_at=now + timedelta(seconds=refresh_seconds),
        scope=scope if isinstance(scope, str) and scope else coros_constants.SCOPE_STRING,
    )


def exchange_code(
    metadata: coros_contracts.CorosOAuthMetadata,
    registration: coros_contracts.CorosClientRegistration,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client: httpx2.Client | None = None,
) -> coros_contracts.CorosTokenSet:
    """Exchange an authorization code for tokens.

    Args:
        metadata: Discovered metadata.
        registration: Registered client.
        code: Authorization code.
        redirect_uri: Registered callback URI.
        code_verifier: PKCE verifier.
        client: Optional HTTP client.

    Returns:
        The token set.
    """
    data = {
        "grant_type": "authorization_code",
        "client_id": registration.client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if registration.client_secret:
        data["client_secret"] = registration.client_secret
    return _token_set(_post_token(metadata, data, client))


def refresh_tokens(
    metadata: coros_contracts.CorosOAuthMetadata,
    registration: coros_contracts.CorosClientRegistration,
    refresh_token: str,
    client: httpx2.Client | None = None,
) -> coros_contracts.CorosTokenSet:
    """Rotate an access/refresh token pair.

    Args:
        metadata: Discovered metadata.
        registration: Registered client.
        refresh_token: Current refresh token.
        client: Optional HTTP client.

    Returns:
        The new token set.
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": registration.client_id,
        "refresh_token": refresh_token,
    }
    if registration.client_secret:
        data["client_secret"] = registration.client_secret
    return _token_set(_post_token(metadata, data, client), fallback_refresh_token=refresh_token)


def revoke_token(
    metadata: coros_contracts.CorosOAuthMetadata,
    registration: coros_contracts.CorosClientRegistration,
    token: str,
    token_type_hint: str,
    client: httpx2.Client | None = None,
) -> None:
    """Best-effort revocation of one token.

    Args:
        metadata: Discovered metadata.
        registration: Registered client.
        token: Token to revoke.
        token_type_hint: ``access_token`` or ``refresh_token``.
        client: Optional HTTP client.
    """
    if metadata.revocation_endpoint is None:
        return
    data = {
        "token": token,
        "token_type_hint": token_type_hint,
        "client_id": registration.client_id,
    }
    if registration.client_secret:
        data["client_secret"] = registration.client_secret
    http = _client(client)
    try:
        http.post(metadata.revocation_endpoint, data=data)
    except (httpx2.TimeoutException, httpx2.RequestError):
        logger.debug("COROS token revocation failed; continuing with local unlink")
    finally:
        if client is None:
            http.close()
