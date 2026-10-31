"""Outbound OpenID Connect calls to an identity provider."""

import hashlib
import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import httpx2
from authlib.integrations.httpx_client import OAuth2Client
from jasil.providers import StateBackendUnavailableError, StateProvider

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.id_token_service as id_token_service

logger = core_logger.get_logger(__name__)


class UpstreamTimeoutError(core_exceptions.DomainError):
    """An identity provider did not answer before the request timed out."""

    status_code = 504
    code = "upstream-timeout"
    title = "Gateway Timeout"
    default_detail = "Identity provider request timed out"


class OidcClientService:
    """Reach an identity provider's OIDC endpoints: discovery, signing keys, token endpoint and userinfo."""

    CACHE_TTL_SECONDS = 3600

    def __init__(self, state: StateProvider, api_version: str) -> None:
        """Initialize the client with the shared state that caches discovery documents and signing keys."""
        self._state = state
        self._api_version = api_version

    @staticmethod
    def _discovery_key(idp_id: int) -> str:
        return f"endurain:idp:oidc-discovery:{idp_id}"

    @staticmethod
    def _jwks_key(jwks_uri: str) -> str:
        uri_hash = hashlib.sha256(jwks_uri.encode()).hexdigest()
        return f"endurain:idp:jwks:{uri_hash}"

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        try:
            value = self._state.get(key)
        except StateBackendUnavailableError as err:
            logger.warning("OIDC cache read failed", exc_info=err)
            return None
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as err:
            logger.warning("OIDC cache contained invalid JSON", exc_info=err)
            return None

    def _write_cache(self, key: str, value: dict[str, Any]) -> None:
        try:
            self._state.set(key, json.dumps(value).encode(), ttl_seconds=self.CACHE_TTL_SECONDS)
        except (StateBackendUnavailableError, TypeError, ValueError) as err:
            logger.warning("OIDC cache write failed", exc_info=err)

    @contextmanager
    def http_client(self) -> Generator[httpx2.Client]:
        """Open a short-lived HTTP client for one outbound request.

        It never follows a redirect: the SSRF guard checks only the URL the caller names, so a redirect
        would send the request, and any secret it carries, to a host the guard never saw.
        """
        with httpx2.Client(
            timeout=10.0,
            follow_redirects=False,
            headers={"User-Agent": f"Endurain/{self._api_version} (OIDC Client)", "Accept": "application/json"},
        ) as client:
            yield client

    def fetch_jwks(self, jwks_uri: str) -> dict[str, Any]:
        """Fetches the JSON Web Key Set (JWKS) from the identity provider.

        This method retrieves the public keys used to verify JWT signatures from the IdP's
        JWKS endpoint. Results are cached for 1 hour to minimize network requests and
        improve performance.

        The JWKS contains one or more public keys in JWK format. Each key has a 'kid'
        (key ID) that matches the 'kid' in JWT headers, allowing us to find the correct
        key for signature verification.

        Args:
            jwks_uri: The JWKS endpoint URL from OIDC discovery (e.g., https://idp.example.com/jwks)

        Returns:
            A dictionary containing the JWKS response with 'keys' array

        Raises:
            domain error: If the JWKS cannot be fetched (network errors, timeouts, invalid JSON)

        Example JWKS response:
        {
            "keys": [
                {
                    "kid": "key-id-1",
                    "kty": "RSA",
                    "use": "sig",
                    "n": "...",  # RSA modulus
                    "e": "..."   # RSA exponent
                }
            ]
        }
        """
        cached = self._read_cache(self._jwks_key(jwks_uri))
        if cached is not None:
            logger.debug("Using cached JWKS")
            return cached

        # Fetch JWKS from IdP
        try:
            # SSRF guard: refuse to dial private/internal
            # IPs even though jwks_uri originates from
            # admin configuration. A misconfigured IdP
            # entry pointing at 127.0.0.1 or the cloud
            # metadata service would otherwise let an
            # attacker pivot via signed token replay.
            # Self-hosted IdPs on private networks can
            # be opted in via SSRF_ALLOWED_HOSTS.
            core_network.reject_private_url(jwks_uri, purpose="oidc_jwks")
            logger.debug("Fetching JWKS from <jwks_uri>", extra=core_logger.context(jwks_uri=jwks_uri))
            with self.http_client() as client:
                response = client.get(jwks_uri)
            response.raise_for_status()

            jwks = response.json()

            # Validate JWKS structure
            if not isinstance(jwks, dict) or "keys" not in jwks:
                logger.debug(
                    "Invalid JWKS format from <jwks_uri>: missing 'keys' array",
                    extra=core_logger.context(jwks_uri=jwks_uri),
                )
                raise core_exceptions.UpstreamError("Identity provider returned invalid JWKS format")

            self._write_cache(self._jwks_key(jwks_uri), jwks)

            logger.debug(
                "Successfully fetched and cached JWKS from <jwks_uri> (<value_2> keys)",
                extra=core_logger.context(jwks_uri=jwks_uri, value_2=len(jwks.get("keys", []))),
            )

            return jwks

        except httpx2.TimeoutException as err:
            logger.debug(
                "Timeout fetching JWKS from <jwks_uri>: <err>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, err=err),
            )
            raise UpstreamTimeoutError("Timeout retrieving signing keys from identity provider") from err
        except httpx2.HTTPStatusError as err:
            logger.debug(
                "HTTP error fetching JWKS from <jwks_uri>: <status_code>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, status_code=err.response.status_code),
            )
            raise core_exceptions.UpstreamError(
                f"Identity provider JWKS endpoint returned error: {err.response.status_code}"
            ) from err
        except json.JSONDecodeError as err:
            logger.debug(
                "Invalid JSON in JWKS response from <jwks_uri>: <err>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, err=err),
            )
            raise core_exceptions.UpstreamError("Identity provider returned invalid JWKS JSON") from err
        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.debug(
                "Unexpected error fetching JWKS from <jwks_uri>: <err>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to retrieve signing keys from identity provider") from err

    def get_oidc_configuration(self, idp: identity_provider_contracts.IdentityProviderState) -> dict[str, Any] | None:
        """Retrieves the OpenID Connect (OIDC) discovery configuration for a given identity provider.

        This method attempts to fetch the OIDC configuration from the provider's well-known discovery endpoint.
        It uses an in-memory cache to avoid redundant network requests and respects a cache TTL (time-to-live).
        If the configuration is cached and not expired, it is returned directly from the cache.
        Otherwise, it fetches the configuration over HTTP, caches it, and returns the result.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing the
                issuer URL and unique ID.

        Returns:
            dict[str, Any] | None: The OIDC discovery configuration as a dictionary if successful, or None if
            fetching fails or the issuer URL is not provided.

        Raises:
            Does not raise exceptions directly; logs errors and returns None on failure.
        """
        if not idp.issuer_url:
            return None

        # Check cache
        cached = self._read_cache(self._discovery_key(idp.id))
        if cached is not None:
            return cached

        # Construct the discovery URL
        discovery_url = f"{idp.issuer_url.rstrip('/')}/.well-known/openid-configuration"

        try:
            # SSRF guard for the admin-supplied issuer
            # URL: see jwks_uri rationale above.
            core_network.reject_private_url(discovery_url, purpose="oidc_discovery")
            # Fetch the configuration
            with self.http_client() as client:
                response = client.get(discovery_url)

            response.raise_for_status()
            config = response.json()

            self._write_cache(self._discovery_key(idp.id), config)

            return config
        except httpx2.HTTPStatusError as err:
            logger.warning(
                "HTTP error fetching OIDC discovery for <name>: <status_code>",
                extra=core_logger.context(name=idp.name, status_code=err.response.status_code),
            )
            return None
        except httpx2.ConnectError as err:
            logger.warning(
                "Connection error fetching OIDC discovery for <name>. URL: <discovery_url>. Error: <err>. "
                "Check if the service is reachable and not using 'localhost' in Docker.",
                extra=core_logger.context(name=idp.name, discovery_url=discovery_url, err=err),
            )
            return None
        except httpx2.RequestError as err:
            logger.warning(
                "Request error fetching OIDC discovery for <name>. URL: <discovery_url>. Error: <err>",
                extra=core_logger.context(name=idp.name, discovery_url=discovery_url, err=err),
            )
            return None
        except core_exceptions.InvalidInputError as err:
            # The SSRF guard refused the URL. Log with an actionable hint for the operator so they
            # know about the SSRF_ALLOWED_HOSTS escape hatch for self-hosted IdPs.
            logger.warning(
                "OIDC discovery for <name> was rejected: <detail>. URL: <discovery_url>. "
                "If this is a self-hosted IdP on a private network, add its host or CIDR to SSRF_ALLOWED_HOSTS.",
                extra=core_logger.context(name=idp.name, detail=err.detail, discovery_url=discovery_url),
            )
            return None
        except Exception as err:
            logger.warning(
                "Failed to fetch OIDC discovery for <name>", exc_info=err, extra=core_logger.context(name=idp.name)
            )
            return None

    def decrypt_client_id(self, idp: identity_provider_contracts.IdentityProviderState) -> str:
        """Decrypts the client ID of the given identity provider.

        Attempts to decrypt the `client_id` attribute of the provided `IdentityProvider` instance
        using Fernet symmetric encryption. If decryption fails or returns an empty value, logs the error
        and raises an HTTP 500 exception indicating a configuration error.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing the
                encrypted client ID.

        Returns:
            str: The decrypted client ID.

        Raises:
            domain error: If decryption fails or returns an empty value, an HTTP 500 error is raised.
        """
        try:
            client_id = core_cryptography.decrypt_token_fernet(idp.client_id)
            if not client_id:
                raise ValueError("Decryption returned empty value")
            return client_id
        except Exception as err:
            logger.debug(
                "Failed to decrypt client ID for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError(
                f"Identity provider {idp.name} configuration error. Please contact administrator."
            ) from err

    def decrypt_client_secret(self, idp: identity_provider_contracts.IdentityProviderState) -> str:
        """Decrypt the IdP client secret using Fernet encryption.

        This helper method centralizes client secret decryption logic to avoid code duplication
        and ensure consistent error handling across all OAuth flows.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider with encrypted client secret.

        Returns:
            str: The decrypted client secret.

        Raises:
            domain error: If decryption fails or returns empty value (500 Internal Server Error).

        Security Note:
            - Decrypted secret only exists in function scope (not logged)
            - Raises domain error to prevent OAuth flows with invalid credentials
        """
        try:
            client_secret = core_cryptography.decrypt_token_fernet(idp.client_secret)
            if not client_secret:
                raise ValueError("Decryption returned empty value")
            return client_secret
        except Exception as err:
            logger.debug(
                "Failed to decrypt client secret for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError(
                f"Identity provider {idp.name} configuration error. Please contact administrator."
            ) from err

    def resolve_token_endpoint(self, idp: identity_provider_contracts.IdentityProviderState) -> str:
        """Resolve the token endpoint URL for an IdP, using OIDC discovery if needed.

        This helper method centralizes token endpoint resolution logic, trying manual
        configuration first and falling back to OIDC discovery if available.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider configuration.

        Returns:
            str: The token endpoint URL.

        Raises:
            domain error: If token endpoint cannot be resolved (500 Internal Server Error).

        Note:
            - Manual configuration (idp.token_endpoint) takes precedence
            - Falls back to OIDC discovery (/.well-known/openid-configuration)
            - Discovery failures are logged but don't block if manual endpoint exists
        """
        token_endpoint = idp.token_endpoint

        # Try OIDC discovery if token endpoint not manually configured
        if not token_endpoint and idp.issuer_url:
            try:
                config = self.get_oidc_configuration(idp)
                if config:
                    token_endpoint = config.get("token_endpoint")
            except Exception as err:
                logger.warning(
                    "OIDC discovery failed for IdP <name> at <issuer_url>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, issuer_url=idp.issuer_url, err=err),
                )
                # Continue - will raise below if still no endpoint

        if not token_endpoint:
            raise core_exceptions.UpstreamError(
                f"Identity provider {idp.name} token endpoint could "
                "not be resolved. Verify the issuer URL is reachable; "
                "if it is on a private network, add its host or CIDR "
                "to SSRF_ALLOWED_HOSTS."
            )

        # SSRF guard: the token endpoint can come from admin config or from
        # the discovery document (whose contents are not otherwise
        # re-validated), so a trusted issuer could still advertise an
        # internal target. Refuse private/internal addresses unless
        # explicitly opted in via SSRF_ALLOWED_HOSTS.
        core_network.reject_private_url(token_endpoint, purpose="oidc_token")

        return token_endpoint

    def create_oauth_client(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str | None = None,
    ) -> OAuth2Client:
        """Create an OAuth2 client for communicating with IdP token endpoints.

        This helper method centralizes OAuth client creation to ensure consistent
        configuration across all OAuth flows.

        Args:
            client_id (str): The OAuth2 client ID.
            client_secret (str): The OAuth2 client secret (decrypted).
            redirect_uri (str | None): The redirect URI (required for authorization code flow).

        Returns:
            OAuth2Client: Configured OAuth2 client instance.

        Note:
            - For authorization code flow: provide redirect_uri
            - For refresh token flow: redirect_uri can be None
        """
        return OAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            timeout=10.0,
            # Like http_client: the token and userinfo calls carry the client secret and the code.
            follow_redirects=False,
            code_challenge_method="S256",
            headers={"User-Agent": f"Endurain/{self._api_version} (OIDC Client)", "Accept": "application/json"},
        )

    def get_userinfo(
        self,
        token_response: dict[str, Any],
        userinfo_endpoint: str | None,
        client: OAuth2Client,
        jwks_uri: str | None,
        expected_issuer: str | None,
        expected_audience: str,
        expected_nonce: str | None = None,
        *,
        require_id_token: bool,
    ) -> dict[str, Any]:
        """Return the identity claims of a signed-in user.

        With ``require_id_token`` the token response must carry an ID token that verifies against the provider's
        signing keys (issuer, audience, expiry and nonce); its claims are the identity and the userinfo endpoint
        only supplements profile fields. Without it (providers that issue no ID token) the userinfo endpoint claims
        are used, and an ID token is verified and merged only when one is present and verifiable. Whenever an
        ID token and userinfo claims are merged, their ``sub`` must match and the ID token claims take precedence.

        Args:
            token_response: The OAuth2 token response containing the access token and, for OIDC, the ID token.
            userinfo_endpoint: The endpoint URL to fetch user information, if available.
            client: The OAuth2 client used to call the userinfo endpoint.
            jwks_uri: The JWKS endpoint URL for verifying ID token signatures.
            expected_issuer: Expected ``iss`` claim value from OIDC discovery.
            expected_audience: Expected ``aud`` claim value (the client id).
            expected_nonce: Nonce stored with the authorization request.
            require_id_token: Whether a verified ID token is mandatory.

        Returns:
            The identity claims.

        Raises:
            UpstreamError: If ``require_id_token`` is set and the issuer, the signing keys or the ID token is missing.
            UnauthenticatedError: If the ID token does not verify, or its ``sub`` differs from the userinfo ``sub``.
            ProcessingError: If no user information can be retrieved.
        """
        if require_id_token:
            if not jwks_uri or not expected_issuer:
                logger.warning("ID token cannot be verified: missing JWKS URI or issuer")
                raise core_exceptions.UpstreamError("Identity provider publishes no issuer or signing keys")
            if not isinstance(token_response.get("id_token"), str):
                logger.warning("Identity provider returned no ID token")
                raise core_exceptions.UpstreamError("Identity provider returned no ID token")

        # Try to get from userinfo endpoint first
        userinfo_claims = None
        if userinfo_endpoint:
            # SSRF guard: the userinfo endpoint can come from admin config or
            # from the discovery document (whose contents are not otherwise
            # re-validated). Because this request carries the OAuth access
            # token in an Authorization header, an internal target could also
            # exfiltrate that token. Refuse private/internal addresses unless
            # explicitly opted in via SSRF_ALLOWED_HOSTS. Raised outside the
            # try/except below so the guard's 4xx is not swallowed as a
            # userinfo fetch failure.
            core_network.reject_private_url(userinfo_endpoint, purpose="oidc_userinfo")
            try:
                # Use the access token to fetch userinfo
                access_token = token_response.get("access_token")
                if access_token:
                    response = client.get(
                        userinfo_endpoint,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    response.raise_for_status()
                    userinfo_claims = response.json()
                    logger.debug("Successfully retrieved userinfo from endpoint")
                else:
                    logger.warning("No access token available for userinfo request")
            except httpx2.TimeoutException as err:
                logger.warning(
                    "Timeout fetching userinfo from endpoint: <err>", exc_info=err, extra=core_logger.context(err=err)
                )
            except httpx2.HTTPStatusError as err:
                logger.warning(
                    "HTTP error <status_code> fetching userinfo",
                    exc_info=err,
                    extra=core_logger.context(status_code=err.response.status_code),
                )
            except httpx2.RequestError as err:
                logger.warning(
                    "Network error fetching userinfo: <err>", exc_info=err, extra=core_logger.context(err=err)
                )
            except Exception as err:
                logger.warning(
                    "Unexpected error fetching userinfo from endpoint: <err>",
                    exc_info=err,
                    extra=core_logger.context(err=err),
                )

        # Verify ID token if present (always do this for security, even if userinfo endpoint succeeded)
        id_token = token_response.get("id_token")
        if id_token and jwks_uri and expected_issuer:
            try:
                # SECURITY: Verify ID token signature using JWKS
                # This replaces the insecure manual base64 decode
                id_token_claims = id_token_service.verify_id_token(
                    self.fetch_jwks,
                    id_token=id_token,
                    jwks_uri=jwks_uri,
                    expected_issuer=expected_issuer,
                    expected_audience=expected_audience,
                    expected_nonce=expected_nonce,
                )

                logger.debug(
                    "Successfully verified ID token for sub=<value_1>",
                    extra=core_logger.context(value_1=id_token_claims.get("sub")),
                )

                # If we got userinfo from endpoint, merge with ID token claims
                # ID token claims take precedence for standard claims (sub, iss, aud)
                if userinfo_claims:
                    # OIDC Core 5.3.2: userinfo is only valid for the subject of the ID token.
                    if userinfo_claims.get("sub") != id_token_claims.get("sub"):
                        logger.warning("Userinfo subject does not match the ID token subject")
                        raise core_exceptions.UnauthenticatedError("Userinfo subject does not match the ID token")
                    merged_claims = {**userinfo_claims, **id_token_claims}
                    logger.debug("Merged userinfo endpoint data with verified ID token claims")
                    return merged_claims
                else:
                    # Only ID token available, return verified claims
                    return id_token_claims

            except core_exceptions.DomainError:
                # Re-raise verification errors (signature failed, expired, etc.)
                # These are security-critical and should not be ignored
                raise
            except Exception as err:
                logger.debug(
                    "Unexpected error verifying ID token: <err>", exc_info=err, extra=core_logger.context(err=err)
                )
                raise core_exceptions.ProcessingError("Failed to verify ID token") from err

        # Providers without an ID token are identified by the userinfo claims alone
        if userinfo_claims:
            return userinfo_claims

        # If ID token exists but we're missing JWKS/issuer info, log warning
        if id_token and (not jwks_uri or not expected_issuer):
            logger.warning(
                "ID token present but cannot verify: missing JWKS URI or issuer. "
                "Configure issuer_url for OIDC discovery."
            )

        # If we get here, we couldn't retrieve or verify any user information
        logger.debug("Failed to retrieve user information from userinfo endpoint or ID token")
        raise core_exceptions.ProcessingError(
            "Unable to retrieve user information from identity provider. Please contact administrator."
        )
