import random
import json
import base64
from enum import Enum
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Request
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt
from joserfc.jwk import RSAKey, ECKey, OctKey
from joserfc.errors import (
    BadSignatureError,
    ExpiredTokenError,
    InvalidClaimError,
    MissingClaimError,
    InvalidPayloadError,
)

import core.config as core_config
import core.cryptography as core_cryptography
import core.logger as core_logger
import auth.identity_providers.models as idp_models
import auth.identity_providers.crud as idp_crud
import users.users.crud as users_crud
import users.users.schema as users_schema
import users.users.models as users_models
import users.users.utils as users_utils
import users.users_identity_providers.crud as user_idp_crud
import users.users_identity_providers.models as user_idp_models
import users.users_identity_providers.utils as user_idp_utils
import auth.password_hasher as auth_password_hasher
import auth.oauth_state.models as oauth_state_models
import auth.oauth_state.crud as oauth_state_crud
import server_settings.schema as server_settings_schema
import server_settings.utils as server_settings_utils


# Constants for token rotation policy
MAX_IDP_TOKEN_AGE_DAYS = 90
TOKEN_EXPIRY_THRESHOLD_MINUTES = 5
TOKEN_REFRESH_RATE_LIMIT_MINUTES = 1
DEFAULT_TOKEN_EXPIRY_SECONDS = 300


class TokenAction(Enum):
    """
    Actions to take for an IdP token based on policy evaluation.

    Attributes:
        SKIP: Token is valid, no action needed
        REFRESH: Token is close to expiry, should be refreshed
        CLEAR: Token is too old or invalid, should be cleared
    """

    SKIP = "skip"
    REFRESH = "refresh"
    CLEAR = "clear"


class IdentityProviderService:

    def __init__(self):
        """
        Initializes the service with in-memory caches for discovery data and their expiry times,
        sets the cache time-to-live (TTL) to 1 hour, and prepares an optional asynchronous HTTP client.
        """
        self._discovery_cache: Dict[int, Dict[str, Any]] = {}
        self._cache_expiry: Dict[int, datetime] = {}
        self._jwks_cache: Dict[str, Dict[str, Any]] = {}  # Cache JWKS by issuer URL
        self._cache_ttl = timedelta(hours=1)
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Asynchronously retrieves or creates an instance of httpx.AsyncClient for making HTTP requests.

        If the HTTP client does not already exist, it initializes a new AsyncClient with a timeout of 10 seconds
        and connection limits (maximum 5 keep-alive connections and 10 total connections). Returns the client instance.

        Returns:
            httpx.AsyncClient: The HTTP client instance for asynchronous requests.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                follow_redirects=True,
                headers={
                    "User-Agent": f"Endurain/{core_config.API_VERSION} (OIDC Client)",
                    "Accept": "application/json",
                },
            )
        return self._http_client

    async def _fetch_jwks(self, jwks_uri: str) -> Dict[str, Any]:
        """
        Fetches the JSON Web Key Set (JWKS) from the identity provider.

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
            HTTPException: If the JWKS cannot be fetched (network errors, timeouts, invalid JSON)

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
        # Check cache first
        now = datetime.now(timezone.utc)
        if jwks_uri in self._jwks_cache:
            cached_data = self._jwks_cache[jwks_uri]
            cached_at = cached_data.get("cached_at")
            if cached_at and (now - cached_at) < self._cache_ttl:
                core_logger.print_to_log(f"Using cached JWKS for {jwks_uri}", "debug")
                return cached_data["jwks"]

        # Fetch JWKS from IdP
        try:
            client = await self._get_http_client()
            core_logger.print_to_log(f"Fetching JWKS from {jwks_uri}", "debug")

            response = await client.get(jwks_uri)
            response.raise_for_status()

            jwks = response.json()

            # Validate JWKS structure
            if not isinstance(jwks, dict) or "keys" not in jwks:
                core_logger.print_to_log(
                    f"Invalid JWKS format from {jwks_uri}: missing 'keys' array",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Identity provider returned invalid JWKS format",
                )

            # Cache the JWKS with timestamp
            self._jwks_cache[jwks_uri] = {"jwks": jwks, "cached_at": now}

            core_logger.print_to_log(
                f"Successfully fetched and cached JWKS from {jwks_uri} "
                f"({len(jwks.get('keys', []))} keys)",
                "debug",
            )

            return jwks

        except httpx.TimeoutException as err:
            core_logger.print_to_log(
                f"Timeout fetching JWKS from {jwks_uri}: {err}", "error", exc=err
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Timeout retrieving signing keys from identity provider",
            )
        except httpx.HTTPStatusError as err:
            core_logger.print_to_log(
                f"HTTP error fetching JWKS from {jwks_uri}: {err.response.status_code}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Identity provider JWKS endpoint returned error: {err.response.status_code}",
            )
        except json.JSONDecodeError as err:
            core_logger.print_to_log(
                f"Invalid JSON in JWKS response from {jwks_uri}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Identity provider returned invalid JWKS JSON",
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error fetching JWKS from {jwks_uri}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve signing keys from identity provider",
            )

    async def _verify_id_token(
        self,
        id_token: str,
        jwks_uri: str,
        expected_issuer: str,
        expected_audience: str,
        expected_nonce: str | None = None,
    ) -> Dict[str, Any]:
        """
        Verifies the ID token's signature and claims using JWKS from the identity provider.

        This method performs comprehensive JWT verification following OIDC Core 1.0 spec:
        1. Fetches the JWKS (public keys) from the IdP
        2. Extracts the 'kid' (key ID) from the JWT header
        3. Finds the matching public key in the JWKS
        4. Imports the key based on its type (RSA, EC, or Oct)
        5. Verifies the JWT signature using joserfc
        6. Validates standard claims (iss, aud, exp, iat)
        7. Validates nonce if provided (required for implicit/hybrid flows)

        This replaces the insecure manual JWT decode that was previously used.

        Args:
            id_token: The ID token JWT string from the token response
            jwks_uri: The JWKS endpoint URL to fetch public keys
            expected_issuer: Expected 'iss' claim value (from OIDC discovery)
            expected_audience: Expected 'aud' claim value (client_id)
            expected_nonce: Expected nonce value from session (optional, but recommended)

        Returns:
            Dictionary containing the verified JWT claims (sub, email, name, etc.)

        Raises:
            HTTPException: If verification fails (invalid signature, expired token, claim mismatch)

        Security Notes:
            - BadSignatureError: Token was tampered with or signed by wrong key
            - ExpiredTokenError: Token is past its 'exp' claim
            - InvalidClaimError: iss/aud/nonce doesn't match expected values
            - MissingClaimError: Required claim is missing
        """
        try:
            # Step 1: Parse JWT header without verification to get 'kid'
            # The ID token has format: header.payload.signature
            parts = id_token.split(".")
            if len(parts) != 3:
                core_logger.print_to_log(
                    f"Invalid JWT format: expected 3 parts, got {len(parts)}", "warning"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid ID token format",
                )

            # Decode header (first part) to get 'kid' and 'alg'
            header_b64 = parts[0]
            # Add padding if necessary
            padding = 4 - len(header_b64) % 4
            if padding != 4:
                header_b64 += "=" * padding

            header_bytes = base64.urlsafe_b64decode(header_b64)
            header = json.loads(header_bytes)

            kid = header.get("kid")
            alg = header.get("alg")

            if not kid:
                core_logger.print_to_log(
                    "ID token header missing 'kid' claim", "warning"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="ID token missing key identifier",
                )

            if not alg:
                core_logger.print_to_log(
                    "ID token header missing 'alg' claim", "warning"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="ID token missing algorithm",
                )

            core_logger.print_to_log(f"ID token header: kid={kid}, alg={alg}", "debug")

            # Step 2: Fetch JWKS from IdP
            jwks = await self._fetch_jwks(jwks_uri)

            # Step 3: Find the matching key in JWKS
            matching_key = None
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    matching_key = key_data
                    break

            if not matching_key:
                core_logger.print_to_log(
                    f"No matching key found in JWKS for kid={kid}", "warning"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="ID token signed with unknown key",
                )

            core_logger.print_to_log(
                f"Found matching key in JWKS: kid={kid}, kty={matching_key.get('kty')}",
                "debug",
            )

            # Step 4: Import the key based on type
            key_type = matching_key.get("kty")

            if key_type == "RSA":
                key = RSAKey.import_key(matching_key)
            elif key_type == "EC":
                key = ECKey.import_key(matching_key)
            elif key_type == "oct":
                key = OctKey.import_key(matching_key)
            else:
                core_logger.print_to_log(
                    f"Unsupported key type in JWKS: {key_type}", "warning"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Unsupported key type: {key_type}",
                )

            # Step 5: Verify signature and decode claims
            # joserfc will verify the signature using the public key
            decoded = jwt.decode(id_token, key)
            claims = decoded.claims

            # Step 5a: Validate claims (iss, aud, exp, iat)
            # This is done separately after decoding in joserfc
            claims_request = jwt.JWTClaimsRegistry(
                iss={"essential": True, "value": expected_issuer},
                aud={"essential": True, "value": expected_audience},
                exp={"essential": True},
                iat={"essential": True},
            )

            # Validate all claims
            claims_request.validate(claims)

            core_logger.print_to_log(
                f"Successfully verified ID token signature for sub={claims.get('sub')}",
                "debug",
            )

            # Step 6: Validate nonce if provided
            # The nonce is used to prevent replay attacks in OAuth2/OIDC flows
            if expected_nonce:
                token_nonce = claims.get("nonce")
                if not token_nonce:
                    core_logger.print_to_log(
                        "ID token missing nonce claim but nonce was expected", "warning"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="ID token missing nonce",
                    )

                if token_nonce != expected_nonce:
                    core_logger.print_to_log(
                        f"ID token nonce mismatch: expected {expected_nonce}, got {token_nonce}",
                        "warning",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="ID token nonce mismatch",
                    )

            # Return verified claims
            return claims

        except BadSignatureError as err:
            core_logger.print_to_log(
                f"ID token signature verification failed: {err}", "warning", exc=err
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ID token signature is invalid",
            )
        except ExpiredTokenError as err:
            core_logger.print_to_log(f"ID token has expired: {err}", "warning", exc=err)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="ID token has expired"
            )
        except InvalidClaimError as err:
            core_logger.print_to_log(
                f"ID token claim validation failed: {err}", "warning", exc=err
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"ID token claim validation failed: {err}",
            )
        except MissingClaimError as err:
            core_logger.print_to_log(
                f"ID token missing required claim: {err}", "warning", exc=err
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"ID token missing required claim: {err}",
            )
        except InvalidPayloadError as err:
            core_logger.print_to_log(
                f"ID token payload is invalid: {err}", "warning", exc=err
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ID token payload is invalid",
            )
        except HTTPException:
            # Re-raise HTTPExceptions from _fetch_jwks or our own validations
            raise
        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error verifying ID token: {err}", "error", exc=err
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to verify ID token",
            )

    async def get_oidc_configuration(
        self, idp: idp_models.IdentityProvider
    ) -> Dict[str, Any] | None:
        """
        Retrieves the OpenID Connect (OIDC) discovery configuration for a given identity provider.
        This method attempts to fetch the OIDC configuration from the provider's well-known discovery endpoint.
        It uses an in-memory cache to avoid redundant network requests and respects a cache TTL (time-to-live).
        If the configuration is cached and not expired, it is returned directly from the cache.
        Otherwise, it fetches the configuration over HTTP, caches it, and returns the result.
        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing the issuer URL and unique ID.
        Returns:
            Dict[str, Any] | None: The OIDC discovery configuration as a dictionary if successful, or None if fetching fails
            or the issuer URL is not provided.
        Raises:
            Does not raise exceptions directly; logs errors and returns None on failure.
        """
        if not idp.issuer_url:
            return None

        # Check cache
        if idp.id in self._discovery_cache:
            if datetime.now(timezone.utc) < self._cache_expiry.get(
                idp.id, datetime.min.replace(tzinfo=timezone.utc)
            ):
                return self._discovery_cache[idp.id]

        # Construct the discovery URL
        discovery_url = f"{idp.issuer_url.rstrip('/')}/.well-known/openid-configuration"

        try:
            # Fetch the configuration
            client = await self._get_http_client()
            response = await client.get(discovery_url)

            response.raise_for_status()
            config = response.json()

            # Cache the configuration
            self._discovery_cache[idp.id] = config
            self._cache_expiry[idp.id] = datetime.now(timezone.utc) + self._cache_ttl

            return config
        except httpx.HTTPStatusError as err:
            core_logger.print_to_log(
                f"HTTP error fetching OIDC discovery for {idp.name}: {err.response.status_code} - {err.response.text}",
                "warning",
            )
            return None
        except httpx.ConnectError as err:
            core_logger.print_to_log(
                f"Connection error fetching OIDC discovery for {idp.name}. "
                f"URL: {discovery_url}. Error: {err}. "
                f"Check if the service is reachable and not using 'localhost' in Docker.",
                "error",
            )
            return None
        except httpx.RequestError as err:
            core_logger.print_to_log(
                f"Request error fetching OIDC discovery for {idp.name}. "
                f"URL: {discovery_url}. Error: {err}",
                "warning",
            )
            return None
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to fetch OIDC discovery for {idp.name}: {err}", "warning"
            )
            return None

    def _get_redirect_uri(self, idp_slug: str) -> str:
        """
        Generates the redirect URI for a given identity provider slug.

        Args:
            idp_slug (str): The slug identifier for the identity provider.

        Returns:
            str: The complete redirect URI for the specified identity provider.
        """
        base_url = core_config.ENDURAIN_HOST
        return f"{base_url}/api/v1/public/idp/callback/{idp_slug}"

    def _decrypt_client_id(self, idp: idp_models.IdentityProvider) -> str:
        """
        Decrypts the client ID of the given identity provider.

        Attempts to decrypt the `client_id` attribute of the provided `IdentityProvider` instance
        using Fernet symmetric encryption. If decryption fails or returns an empty value, logs the error
        and raises an HTTP 500 exception indicating a configuration error.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing the encrypted client ID.

        Returns:
            str: The decrypted client ID.

        Raises:
            HTTPException: If decryption fails or returns an empty value, an HTTP 500 error is raised.
        """
        try:
            client_id = core_cryptography.decrypt_token_fernet(idp.client_id)
            if not client_id:
                raise ValueError("Decryption returned empty value")
            return client_id
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to decrypt client ID for IdP {idp.name}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Identity provider {idp.name} configuration error. Please contact administrator.",
            ) from err

    def _decrypt_client_secret(self, idp: idp_models.IdentityProvider) -> str:
        """
        Decrypt the IdP client secret using Fernet encryption.

        This helper method centralizes client secret decryption logic to avoid code duplication
        and ensure consistent error handling across all OAuth flows.

        Args:
            idp (idp_models.IdentityProvider): The identity provider with encrypted client secret.

        Returns:
            str: The decrypted client secret.

        Raises:
            HTTPException: If decryption fails or returns empty value (500 Internal Server Error).

        Security Note:
            - Decrypted secret only exists in function scope (not logged)
            - Raises HTTPException to prevent OAuth flows with invalid credentials
        """
        try:
            client_secret = core_cryptography.decrypt_token_fernet(idp.client_secret)
            if not client_secret:
                raise ValueError("Decryption returned empty value")
            return client_secret
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to decrypt client secret for IdP {idp.name}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Identity provider {idp.name} configuration error. Please contact administrator.",
            ) from err

    async def _resolve_token_endpoint(self, idp: idp_models.IdentityProvider) -> str:
        """
        Resolve the token endpoint URL for an IdP, using OIDC discovery if needed.

        This helper method centralizes token endpoint resolution logic, trying manual
        configuration first and falling back to OIDC discovery if available.

        Args:
            idp (idp_models.IdentityProvider): The identity provider configuration.

        Returns:
            str: The token endpoint URL.

        Raises:
            HTTPException: If token endpoint cannot be resolved (500 Internal Server Error).

        Note:
            - Manual configuration (idp.token_endpoint) takes precedence
            - Falls back to OIDC discovery (/.well-known/openid-configuration)
            - Discovery failures are logged but don't block if manual endpoint exists
        """
        token_endpoint = idp.token_endpoint

        # Try OIDC discovery if token endpoint not manually configured
        if not token_endpoint and idp.issuer_url:
            try:
                config = await self.get_oidc_configuration(idp)
                if config:
                    token_endpoint = config.get("token_endpoint")
            except Exception as err:
                core_logger.print_to_log(
                    f"OIDC discovery failed for IdP {idp.name} at {idp.issuer_url}: {err}",
                    "warning",
                    exc=err,
                )
                # Continue - will raise below if still no endpoint

        if not token_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Identity provider {idp.name} missing token endpoint configuration.",
            )

        return token_endpoint

    def _create_oauth_client(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str | None = None,
    ) -> AsyncOAuth2Client:
        """
        Create an OAuth2 client for communicating with IdP token endpoints.

        This helper method centralizes OAuth client creation to ensure consistent
        configuration across all OAuth flows.

        Args:
            client_id (str): The OAuth2 client ID.
            client_secret (str): The OAuth2 client secret (decrypted).
            redirect_uri (str | None): The redirect URI (required for authorization code flow).

        Returns:
            AsyncOAuth2Client: Configured OAuth2 client instance.

        Note:
            - For authorization code flow: provide redirect_uri
            - For refresh token flow: redirect_uri can be None
        """
        return AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )

    async def initiate_login(
        self,
        idp: idp_models.IdentityProvider,
        request: Request,
        db: Session,
        redirect_path: str | None = None,
        oauth_state_id: str | None = None,
    ) -> str:
        """
        Initiates the OAuth2/OIDC login process for the given identity provider.

        This method prepares the authorization URL for the user to authenticate with the specified
        identity provider (IdP). It handles endpoint discovery and authorization URL construction.


        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing configuration details.
            request (Request): The current HTTP request object.
            db (Session): The database session.
            redirect_path (str | None): Optional frontend path to redirect to after successful login.
            oauth_state_id (str | None): Database OAuth state ID (from PKCE flow).

        Returns:
            str: The authorization URL to which the user should be redirected to initiate login.

        Raises:
            HTTPException: If the identity provider is not properly configured or if an error occurs during initiation.
        """
        try:
            client_id = self._decrypt_client_id(idp)

            # Get endpoints
            authorization_endpoint = idp.authorization_endpoint

            # Try OIDC discovery if issuer URL is provided
            if not authorization_endpoint and idp.issuer_url:
                config = await self.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Identity provider not properly configured",
                )

            # Retrieve database-backed OAuth state (mandatory for all clients)
            if not oauth_state_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OAuth state ID is required (PKCE mandatory)",
                )

            oauth_state_obj = oauth_state_crud.get_oauth_state_by_id(oauth_state_id, db)
            if not oauth_state_obj:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OAuth state not found",
                )

            state = oauth_state_id
            nonce = oauth_state_obj.nonce

            # Build authorization URL
            redirect_uri = self._get_redirect_uri(idp.slug)
            scopes = idp.scopes or "openid profile email"

            client = AsyncOAuth2Client(
                client_id=client_id, redirect_uri=redirect_uri, scope=scopes
            )

            authorization_url, _ = client.create_authorization_url(
                authorization_endpoint, state=state, nonce=nonce
            )

            return authorization_url

        except HTTPException:
            raise
        except Exception as err:
            core_logger.print_to_log(
                f"Error initiating OAuth login for IdP {idp.name}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate SSO login",
            ) from err

    async def initiate_link(
        self,
        idp: idp_models.IdentityProvider,
        request: Request,
        user_id: int,
        db: Session,
        oauth_state_id: str | None = None,
    ) -> str:
        """
        Initiates the OAuth/OIDC authorization flow for linking an identity provider to an existing user account.
        This method generates the authorization URL that redirects the user to the identity provider's
        login page. Uses database-backed OAuth state for security and replay protection.

        Args:
            idp (idp_models.IdentityProvider): The identity provider configuration object containing
                client credentials, endpoints, and other OAuth/OIDC settings.
            request (Request): The FastAPI request object used to access and store session data.
            user_id (int): The ID of the authenticated user who is linking their account to the
                identity provider.
            db (Session): The database session for database operations.
            oauth_state_id (str | None): Database OAuth state ID (required for secure linking).

        Returns:
            str: The authorization URL to redirect the user to for identity provider authentication.

        Raises:
            HTTPException:
                - 500 status code if the identity provider is not properly configured (missing
                  authorization endpoint).
                - 500 status code if OAuth state ID is missing or invalid.
                - 500 status code if any unexpected error occurs during the OAuth flow initiation.

        Note:
            - If authorization_endpoint is not directly configured, the method attempts OIDC
              discovery using the issuer_url.
            - OAuth state is stored in database with user_id to indicate link mode.
        """
        try:
            client_id = self._decrypt_client_id(idp)

            # Get endpoints
            authorization_endpoint = idp.authorization_endpoint

            # Try OIDC discovery if issuer URL is provided
            if not authorization_endpoint and idp.issuer_url:
                config = await self.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Identity provider not properly configured",
                )

            # Retrieve database-backed OAuth state (required for link mode)
            if not oauth_state_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OAuth state ID is required for secure linking",
                )

            oauth_state_obj = oauth_state_crud.get_oauth_state_by_id(oauth_state_id, db)
            if not oauth_state_obj:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OAuth state not found",
                )

            # Validate user_id matches (security check for link mode)
            if oauth_state_obj.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OAuth state user mismatch",
                )

            state = oauth_state_id
            nonce = oauth_state_obj.nonce

            # Build authorization URL
            redirect_uri = self._get_redirect_uri(idp.slug)
            scopes = idp.scopes or "openid profile email"

            client = AsyncOAuth2Client(
                client_id=client_id, redirect_uri=redirect_uri, scope=scopes
            )

            authorization_url, _ = client.create_authorization_url(
                authorization_endpoint, state=state, nonce=nonce
            )

            return authorization_url

        except HTTPException:
            raise
        except Exception as err:
            core_logger.print_to_log(
                f"Error initiating OAuth link for IdP {idp.name}, user {user_id}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate identity provider linking",
            ) from err

    async def handle_callback(
        self,
        idp: idp_models.IdentityProvider,
        code: str,
        state: str,
        request: Request,
        password_hasher: auth_password_hasher.PasswordHasher,
        db: Session,
        oauth_state: oauth_state_models.OAuthState,
    ) -> Dict[str, Any]:
        """
        Handle the OAuth2/OIDC callback from an identity provider.
        This method processes the authorization code received from an identity provider,
        validates the state parameter, exchanges the code for tokens, retrieves user
        information, and either creates/updates a user session (login mode) or links
        the identity provider to an existing user account (link mode).
        Args:
            idp (idp_models.IdentityProvider): The identity provider configuration object.
            code (str): The authorization code returned by the identity provider.
            state (str): The state parameter for CSRF protection (database state ID).
            request (Request): The FastAPI/Starlette request object.
            password_hasher (auth_password_hasher.PasswordHasher): Password hasher instance
                for user authentication operations.
            db (Session): SQLAlchemy database session.
            oauth_state (oauth_state_models.OAuthState): Database OAuth state object.

        Returns:
            Dict[str, Any]: A dictionary containing:
                - user: The authenticated or linked user object
                - token_data: OAuth2 token response (access_token, refresh_token, etc.)
                - userinfo: User information claims from the identity provider
                - mode (optional): "link" if this was a link operation (not present for login)

        Raises:
            HTTPException: With appropriate status codes for various error conditions:
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
        try:
            # Use database-backed OAuth state (mandatory for all clients)
            redirect_path = oauth_state.redirect_path
            client_type = oauth_state.client_type

            core_logger.print_to_log(
                f"Using database OAuth state for IdP {idp.name} (client_type={client_type})",
                "debug",
            )

            # Detect link mode from OAuth state (user_id indicates authenticated user linking)
            is_link_mode = oauth_state.user_id is not None
            link_user_id = oauth_state.user_id

            if is_link_mode:
                # Link mode: OAuth state was created during authenticated linking request
                # The user_id in oauth_state proves the user initiated this link
                core_logger.print_to_log(
                    f"Link mode detected for IdP {idp.name}, user_id={link_user_id}",
                    "debug",
                )

            # Decrypt credentials and resolve endpoints using helper methods
            client_id = self._decrypt_client_id(idp)
            client_secret = self._decrypt_client_secret(idp)
            token_endpoint = await self._resolve_token_endpoint(idp)

            # Get OIDC configuration (for userinfo, jwks_uri, issuer)
            userinfo_endpoint = idp.userinfo_endpoint
            jwks_uri = None
            expected_issuer = None

            if idp.issuer_url:
                try:
                    config = await self.get_oidc_configuration(idp)
                    if config:
                        # Get userinfo endpoint if not manually configured
                        if not userinfo_endpoint:
                            userinfo_endpoint = config.get("userinfo_endpoint")

                        # Get JWKS URI for ID token verification
                        jwks_uri = config.get("jwks_uri")
                        expected_issuer = config.get("issuer")

                        core_logger.print_to_log(
                            f"OIDC discovery complete for {idp.name}: "
                            f"userinfo={bool(userinfo_endpoint)}, "
                            f"jwks_uri={bool(jwks_uri)}, "
                            f"issuer={bool(expected_issuer)}",
                            "debug",
                        )
                except Exception as err:
                    core_logger.print_to_log(
                        f"OIDC discovery failed for IdP {idp.name}: {err}",
                        "warning",
                        exc=err,
                    )

            # Retrieve nonce from database state
            expected_nonce = oauth_state.nonce

            # Exchange code for tokens
            redirect_uri = self._get_redirect_uri(idp.slug)

            try:
                client = self._create_oauth_client(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                )

                token_response = await client.fetch_token(
                    token_endpoint, grant_type="authorization_code", code=code
                )
            except httpx.TimeoutException as err:
                core_logger.print_to_log(
                    f"Timeout connecting to IdP {idp.name} token endpoint: {err}",
                    "error",
                    exc=err,
                )
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Identity provider {idp.name} is not responding. Please try again later.",
                ) from err
            except httpx.HTTPStatusError as err:
                core_logger.print_to_log(
                    f"HTTP error from IdP {idp.name} token endpoint: {err.response.status_code} - {err.response.text}",
                    "error",
                    exc=err,
                )
                # Check for common OAuth2 error responses
                if err.response.status_code == 400:
                    detail = "Authorization code is invalid or expired. Please try logging in again."
                elif err.response.status_code == 401:
                    detail = f"Identity provider {idp.name} rejected the authentication request. Please contact administrator."
                else:
                    detail = f"Identity provider {idp.name} returned an error. Please try again later."

                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=detail,
                ) from err
            except httpx.RequestError as err:
                core_logger.print_to_log(
                    f"Network error connecting to IdP {idp.name}: {err}",
                    "error",
                    exc=err,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Unable to connect to identity provider {idp.name}. Please check your network connection.",
                ) from err
            except Exception as err:
                core_logger.print_to_log(
                    f"Unexpected error during token exchange with IdP {idp.name}: {err}",
                    "error",
                    exc=err,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to complete authentication. Please try again.",
                ) from err

            # Get user information with ID token verification
            userinfo = await self._get_userinfo(
                token_response=token_response,
                userinfo_endpoint=userinfo_endpoint,
                client=client,
                jwks_uri=jwks_uri,
                expected_issuer=expected_issuer,
                expected_audience=client_id,
                expected_nonce=expected_nonce,
            )

            # Extract subject (unique user identifier)
            subject = userinfo.get("sub") or userinfo.get("id")
            if not subject:
                core_logger.print_to_log(
                    f"IdP {idp.name} did not provide 'sub' or 'id' claim in userinfo: {list(userinfo.keys())}",
                    "error",
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Identity provider {idp.name} did not provide required user identifier. Please contact administrator.",
                )

            # Handle link mode differently from login mode
            if is_link_mode and link_user_id:
                # LINK MODE: Associate IdP with existing authenticated user

                # Verify user exists
                user = users_crud.get_user_by_id(link_user_id, db)
                if not user:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found",
                    )

                # Check if this IdP subject is already linked to ANY user
                existing_link = (
                    user_idp_crud.get_user_identity_provider_by_subject_and_idp_id(
                        idp.id, subject, db
                    )
                )
                if existing_link:
                    # Check if it's already linked to THIS user
                    if existing_link.user_id == link_user_id:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"This {idp.name} account is already linked to your account",
                        )
                    else:
                        # Linked to a DIFFERENT user - security issue
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"This {idp.name} account is already linked to another user",
                        )

                # Create the link
                user_idp_crud.create_user_identity_provider(
                    user_id=link_user_id, idp_id=idp.id, idp_subject=subject, db=db
                )

                # Store IdP tokens for future use
                await self._store_idp_tokens(link_user_id, idp.id, token_response, db)

                core_logger.print_to_log(
                    f"User {user.username} (id={link_user_id}) linked IdP {idp.name} (subject={subject})",
                    "info",
                )

                # Return special structure for link mode (no new session created)
                return {
                    "user": user,
                    "token_data": token_response,
                    "userinfo": userinfo,
                    "mode": "link",  # Indicate this was a link operation
                }

            else:
                # LOGIN MODE: Find or create user and establish session
                user = await self._find_or_create_user(
                    idp, subject, userinfo, password_hasher, db
                )

                # Store IdP tokens for future session renewal
                await self._store_idp_tokens(user.id, idp.id, token_response, db)

                core_logger.print_to_log(
                    f"User {user.username} authenticated via IdP {idp.name}", "info"
                )

                return {
                    "user": user,
                    "token_data": token_response,
                    "userinfo": userinfo,
                    "redirect_path": redirect_path,
                    "client_type": client_type,
                }

        except HTTPException:
            # Re-raise HTTPExceptions as-is (already have proper status codes and messages)
            raise
        except Exception as err:
            # Catch-all for unexpected errors
            core_logger.print_to_log(
                f"Unexpected error handling OAuth callback for IdP {idp.name}: {err}",
                "error",
                exc=err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during authentication with {idp.name}. Please try again or contact administrator.",
            ) from err

    async def _get_userinfo(
        self,
        token_response: Dict[str, Any],
        userinfo_endpoint: str | None,
        client: AsyncOAuth2Client,
        jwks_uri: str | None,
        expected_issuer: str | None,
        expected_audience: str,
        expected_nonce: str | None = None,
    ) -> Dict[str, Any]:
        """
        Retrieve user information from an identity provider using the provided token response.

        This method first attempts to fetch user information from the given `userinfo_endpoint` using the provided OAuth2 client.
        If the endpoint is unavailable or the request fails, it falls back to extracting claims from the `id_token` in the token response,
        verifying the ID token signature using JWKS before returning the claims.

        Security Enhancement:
        - ID tokens are now cryptographically verified using joserfc and JWKS
        - Signature verification prevents token forgery and tampering
        - Claims validation ensures token integrity (iss, aud, exp, nonce)
        - This replaces the insecure manual base64 decode previously used

        Args:
            token_response (Dict[str, Any]): The OAuth2 token response containing access and/or ID tokens.
            userinfo_endpoint (str | None): The endpoint URL to fetch user information, if available.
            client (AsyncOAuth2Client): The asynchronous OAuth2 client used to make HTTP requests.
            jwks_uri (str | None): The JWKS endpoint URL for verifying ID token signatures.
            expected_issuer (str | None): Expected 'iss' claim value from OIDC discovery.
            expected_audience (str): Expected 'aud' claim value (typically the client_id).
            expected_nonce (str | None): Expected nonce value from session (optional, but recommended).

        Returns:
            Dict[str, Any]: The user information claims retrieved from the identity provider.

        Raises:
            HTTPException: If user information cannot be retrieved from either the userinfo endpoint or the ID token,
                          or if ID token verification fails.
        """
        # Try to get from userinfo endpoint first
        userinfo_claims = None
        if userinfo_endpoint:
            try:
                # Use the access token to fetch userinfo
                access_token = token_response.get("access_token")
                if access_token:
                    response = await client.get(
                        userinfo_endpoint,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    response.raise_for_status()
                    userinfo_claims = response.json()
                    core_logger.print_to_log(
                        "Successfully retrieved userinfo from endpoint", "debug"
                    )
                else:
                    core_logger.print_to_log(
                        "No access token available for userinfo request", "warning"
                    )
            except httpx.TimeoutException as err:
                core_logger.print_to_log(
                    f"Timeout fetching userinfo from endpoint: {err}",
                    "warning",
                    exc=err,
                )
            except httpx.HTTPStatusError as err:
                core_logger.print_to_log(
                    f"HTTP error {err.response.status_code} fetching userinfo: {err.response.text}",
                    "warning",
                    exc=err,
                )
            except httpx.RequestError as err:
                core_logger.print_to_log(
                    f"Network error fetching userinfo: {err}", "warning", exc=err
                )
            except Exception as err:
                core_logger.print_to_log(
                    f"Unexpected error fetching userinfo from endpoint: {err}",
                    "warning",
                    exc=err,
                )

        # Verify ID token if present (always do this for security, even if userinfo endpoint succeeded)
        id_token = token_response.get("id_token")
        if id_token and jwks_uri and expected_issuer:
            try:
                # SECURITY: Verify ID token signature using JWKS
                # This replaces the insecure manual base64 decode
                id_token_claims = await self._verify_id_token(
                    id_token=id_token,
                    jwks_uri=jwks_uri,
                    expected_issuer=expected_issuer,
                    expected_audience=expected_audience,
                    expected_nonce=expected_nonce,
                )

                core_logger.print_to_log(
                    f"Successfully verified ID token for sub={id_token_claims.get('sub')}",
                    "debug",
                )

                # If we got userinfo from endpoint, merge with ID token claims
                # ID token claims take precedence for standard claims (sub, iss, aud)
                if userinfo_claims:
                    # Merge: userinfo endpoint data + ID token verified claims
                    # ID token claims override for security-critical fields
                    merged_claims = {**userinfo_claims, **id_token_claims}
                    core_logger.print_to_log(
                        "Merged userinfo endpoint data with verified ID token claims",
                        "debug",
                    )
                    return merged_claims
                else:
                    # Only ID token available, return verified claims
                    return id_token_claims

            except HTTPException:
                # Re-raise verification errors (signature failed, expired, etc.)
                # These are security-critical and should not be ignored
                raise
            except Exception as err:
                core_logger.print_to_log(
                    f"Unexpected error verifying ID token: {err}", "error", exc=err
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to verify ID token",
                )

        # If we got userinfo from endpoint but no ID token, return userinfo
        if userinfo_claims:
            return userinfo_claims

        # If ID token exists but we're missing JWKS/issuer info, log warning
        if id_token and (not jwks_uri or not expected_issuer):
            core_logger.print_to_log(
                "ID token present but cannot verify: missing JWKS URI or issuer. "
                "Configure issuer_url for OIDC discovery.",
                "warning",
            )

        # If we get here, we couldn't retrieve or verify any user information
        core_logger.print_to_log(
            "Failed to retrieve user information from userinfo endpoint or ID token",
            "error",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve user information from identity provider. Please contact administrator.",
        )

    async def _store_idp_tokens(
        self,
        user_id: int,
        idp_id: int,
        token_response: Dict[str, Any],
        db: Session,
    ) -> None:
        """
        Store IdP tokens after successful authentication.

        This method extracts the refresh token from the OAuth token response, encrypts it,
        and stores it along with metadata for future session renewal. If no refresh token
        is provided by the IdP, the method logs a debug message and returns gracefully.

        Args:
            user_id (int): The ID of the authenticated user.
            idp_id (int): The ID of the identity provider.
            token_response (Dict[str, Any]): The OAuth token response from the IdP containing
                access_token, refresh_token (optional), and expires_in.
            db (Session): The database session for storing tokens.

        Returns:
            None

        Security Note:
            - The refresh token is encrypted using Fernet before storage
            - If encryption fails, the error is logged but authentication continues
            - Missing refresh tokens are handled gracefully (not all IdPs provide them)

        Example token_response:
            {
                "access_token": "eyJhbGci...",
                "refresh_token": "eyJhbGci...",  # Optional
                "expires_in": 300,
                "token_type": "Bearer"
            }
        """
        # Extract refresh token from response
        refresh_token = token_response.get("refresh_token")

        if not refresh_token:
            core_logger.print_to_log(
                f"No refresh token provided by IdP (user_id={user_id}, idp_id={idp_id}). "
                "User will need to re-authenticate when session expires.",
                "debug",
            )
            return

        try:
            # Encrypt the refresh token using Fernet
            encrypted_refresh = core_cryptography.encrypt_token_fernet(refresh_token)

            if not encrypted_refresh:
                core_logger.print_to_log(
                    f"Failed to encrypt refresh token for user {user_id}, idp {idp_id}. "
                    "Token will not be stored.",
                    "warning",
                )
                return

            # Calculate when the access token expires
            expires_in = token_response.get("expires_in", DEFAULT_TOKEN_EXPIRY_SECONDS)
            access_token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expires_in
            )

            # Store encrypted token and metadata in database
            user_idp_crud.store_user_identity_provider_tokens(
                user_id=user_id,
                idp_id=idp_id,
                encrypted_refresh_token=encrypted_refresh,
                access_token_expires_at=access_token_expires_at,
                db=db,
            )

            core_logger.print_to_log(
                f"Stored IdP refresh token for user {user_id}, idp {idp_id} "
                f"(expires at {access_token_expires_at.isoformat()})",
                "debug",
            )

        except Exception as err:
            # Log the error but don't fail the authentication flow
            core_logger.print_to_log(
                f"Error storing IdP refresh token for user {user_id}: {err}",
                "error",
                exc=err,
            )
            # Authentication succeeds even if token storage fails
            # User will need to re-auth when session expires, but that's acceptable

    def _map_user_claims(
        self, idp: idp_models.IdentityProvider, claims: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Maps user claims from an identity provider to a standardized user dictionary.

        This method takes an identity provider configuration and a dictionary of claims,
        then maps the claims to standard user fields (such as 'username', 'email', and 'name')
        using both default and custom mappings defined in the identity provider.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance containing optional custom user mapping.
            claims (Dict[str, Any]): The dictionary of claims received from the identity provider.

        Returns:
            Dict[str, Any]: A dictionary mapping standard user fields to their corresponding claim values.
        """
        # Default mapping
        default_mapping = {
            "username": ["preferred_username", "username", "email", "sub"],
            "email": ["email", "mail"],
            "name": ["name", "display_name", "full_name", "displayName"],
        }

        # Merge with custom mapping
        mapping = {**default_mapping, **(idp.user_mapping or {})}

        result = {}
        for field, claim_names in mapping.items():
            if isinstance(claim_names, str):
                claim_names = [claim_names]
            for claim in claim_names:
                if claim in claims and claims[claim]:
                    result[field] = claims[claim]
                    break

        return result

    async def _find_or_create_user(
        self,
        idp: idp_models.IdentityProvider,
        subject: str,
        userinfo: Dict[str, Any],
        password_hasher: auth_password_hasher.PasswordHasher,
        db: Session,
    ) -> users_models.Users:
        """
        Finds an existing user linked to the given identity provider and subject, or creates a new user if allowed.

        This method attempts to:
        1. Find a user by their identity provider (IdP) link using the subject identifier.
        2. If not found, find a user by email and link their account to the IdP.
        3. If still not found and auto-creation is enabled, create a new user from the IdP information.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            userinfo (Dict[str, Any]): User information/claims from the IdP.
            password_hasher (auth_password_hasher.PasswordHasher): The password hasher instance.
            db (Session): Database session.

        Returns:
            users_models.Users: The found or newly created user instance.

        Raises:
            HTTPException: If user creation is disabled for the identity provider and no existing user is found.
        """
        # Try to find existing user by IdP link
        link = user_idp_crud.get_user_identity_provider_by_subject_and_idp_id(
            idp.id, subject, db
        )

        if link:
            user = link.user
            # Update last login timestamp
            user_idp_crud.update_user_identity_provider_last_login(
                link.user_id, idp.id, db
            )

            # Update user info if sync is enabled
            if idp.sync_user_info:
                user = await self._update_user_from_idp(user, idp, userinfo, db)
            return user

        # Try to find by email (for linking existing accounts)
        mapped_data = self._map_user_claims(idp, userinfo)
        email = mapped_data.get("email")

        if email:
            user = users_crud.get_user_by_email(email, db)
            if user:
                # Link existing account to IdP
                user_idp_crud.create_user_identity_provider(
                    user.id, idp.id, subject, db
                )

                core_logger.print_to_log(
                    f"Linked existing user {user.username} to IdP {idp.name}", "info"
                )

                # Update user info if sync is enabled
                if idp.sync_user_info:
                    user = await self._update_user_from_idp(user, idp, userinfo, db)
                return user

        # Create new user if auto-creation is enabled
        if not idp.auto_create_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account creation is disabled for this identity provider",
            )

        user = await self._create_user_from_idp(
            idp, subject, mapped_data, password_hasher, db
        )

        return user

    async def _create_user_from_idp(
        self,
        idp: idp_models.IdentityProvider,
        subject: str,
        mapped_data: Dict[str, Any],
        password_hasher: auth_password_hasher.PasswordHasher,
        db: Session,
    ) -> users_models.Users:
        """
        Creates a new user in the database based on identity provider (IdP) information.

        This method generates a unique username, creates a user with mapped data from the IdP
        using the existing CRUD layer, and links the user to the IdP subject. The password is
        randomly generated and properly hashed but not intended for SSO users. The user's email
        is marked as verified since we trust the IdP's verification.

        Args:
            idp (idp_models.IdentityProvider): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            mapped_data (Dict[str, Any]): User data mapped from the IdP (e.g., username, email, name).
            password_hasher (auth_password_hasher.PasswordHasher): The password hasher instance.
            db (Session): The database session.

        Returns:
            users_models.Users: The newly created user instance.

        Raises:
            HTTPException: If user creation fails (e.g., duplicate username/email).
        """
        # Generate a random password (won't be used for SSO users)
        random_password = password_hasher.generate_password(length=16)

        # Ensure username is unique
        base_username = mapped_data.get("username", f"user_{subject[:8]}")
        username = base_username
        while users_crud.get_user_by_username(username, db):
            username = f"{base_username}_{str(random.randint(100000, 999999))}"

        # Create user signup schema
        user_signup = users_schema.UsersSignup(
            username=username,
            email=mapped_data.get("email", f"{username}@sso.local"),
            city=mapped_data.get("city", None),
            birthdate=mapped_data.get("birthdate", None),
            name=mapped_data.get("name", username),
            password=random_password,
            preferred_language=users_schema.Language.ENGLISH_USA,
            gender=users_schema.Gender.UNSPECIFIED,
            units=server_settings_schema.Units.METRIC,
            height=mapped_data.get("height", None),
            max_heart_rate=mapped_data.get("max_heart_rate", None),
            first_day_of_week=users_schema.WeekDay.MONDAY,
            currency=server_settings_schema.Currency.EURO,
        )

        server_settings = server_settings_utils.get_server_settings_or_404(db)

        created_user = users_crud.create_signup_user(
            user_signup, server_settings, password_hasher, db
        )

        # Create default data for the user
        users_utils.create_user_default_data(created_user.id, db)

        # Create the IdP link
        user_idp_crud.create_user_identity_provider(
            created_user.id, idp.id, subject, db
        )

        core_logger.print_to_log(
            f"Created new user {created_user.username} from IdP {idp.name}", "info"
        )

        return created_user

    async def _update_user_from_idp(
        self,
        user: users_models.Users,
        idp: idp_models.IdentityProvider,
        userinfo: Dict[str, Any],
        db: Session,
    ) -> users_models.Users:
        """
        Updates the user's information based on claims received from an identity provider (IdP).

        This method syncs user profile information from the IdP to the local user account when
        IdP sync is enabled. It performs the following steps:
        1. Maps claims from IdP userinfo to standard user fields (email, name)
        2. Validates email changes - checks if new email is already in use by another user
        3. Skips email updates if conflict detected and logs the issue
        4. Converts user ORM model to Pydantic schema
        5. Applies updates and delegates persistence to the CRUD layer

        Args:
            user (users_models.Users): The user ORM instance to update.
            idp (idp_models.IdentityProvider): The identity provider instance with user_mapping config.
            userinfo (Dict[str, Any]): The user information claims received from the IdP.
            db (Session): The SQLAlchemy database session.

        Returns:
            users_models.Users: The updated user ORM instance from database.
        """
        mapped_data = self._map_user_claims(idp, userinfo)

        # Build updates
        updates = {}

        print("Mapped data from IdP:", mapped_data)

        # Check email - verify not already in use
        if "email" in mapped_data and mapped_data["email"] != user.email:
            existing_user = users_crud.get_user_by_email(mapped_data["email"], db)
            if existing_user and existing_user.id != user.id:
                core_logger.print_to_log(
                    f"Cannot sync email from IdP {idp.name}: "
                    f"{mapped_data['email']} already in use by another user",
                    "warning",
                )
            else:
                core_logger.print_to_log(
                    f"Syncing email for user {user.username} from IdP {idp.name}: "
                    f"{user.email} -> {mapped_data['email']}",
                    "debug",
                )
                updates["email"] = mapped_data["email"].strip()

        # Check name
        if "name" in mapped_data and mapped_data["name"] != user.name:
            core_logger.print_to_log(
                f"Syncing name for user {user.username} from IdP {idp.name}: "
                f"{user.name} -> {mapped_data['name']}",
                "debug",
            )
            updates["name"] = mapped_data["name"].strip()

        # Only call CRUD if there are updates
        if updates:
            print("Applying updates to user:", updates)
            user_read = users_schema.UsersRead.model_validate(user)
            for field, value in updates.items():
                setattr(user_read, field, value)

            user = await users_crud.edit_user(user.id, user_read, db)

        return user

    async def refresh_idp_session(
        self,
        user_id: int,
        idp_id: int,
        db: Session,
    ) -> Dict[str, Any] | None:
        """
        Attempt to refresh a user's IdP session using stored refresh token.

        This method enables silent session renewal without re-prompting the user to login.
        It retrieves the stored encrypted refresh token, decrypts it, and exchanges it
        with the IdP for new access and refresh tokens. If successful, the new tokens
        are encrypted and stored.

        Args:
            user_id (int): The ID of the user whose session should be refreshed.
            idp_id (int): The ID of the identity provider.
            db (Session): The database session for token retrieval and updates.

        Returns:
            Dict[str, Any] | None: A dictionary containing the new token response if successful,
                or None if the refresh failed (expired/revoked token, network error, etc.).

        Raises:
            HTTPException: If the IdP is not found, disabled, or misconfigured.

        Example return value:
            {
                "access_token": "eyJhbGci...",
                "refresh_token": "eyJhbGci...",  # May be the same or new token
                "expires_in": 300,
                "token_type": "Bearer"
            }

        Security Notes:
            - Refresh token is decrypted only in memory, never logged
            - If refresh fails (invalid/revoked), the stored token is cleared
            - Network errors do not clear the token (IdP may be temporarily down)
        """
        # Get the IdP configuration
        idp = idp_crud.get_identity_provider(idp_id, db)
        if not idp or not idp.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Identity provider (ID: {idp_id}) not found or disabled",
            )

        # Get the encrypted refresh token from database
        encrypted_refresh_token = user_idp_utils.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
            user_id, idp_id, db
        )

        if not encrypted_refresh_token:
            core_logger.print_to_log(
                f"No refresh token stored for user {user_id}, idp {idp_id}. "
                "Cannot refresh session.",
                "debug",
            )
            return None

        # Decrypt the refresh token
        try:
            refresh_token = core_cryptography.decrypt_token_fernet(
                encrypted_refresh_token
            )
            if not refresh_token:
                raise ValueError("Decryption returned empty value")
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to decrypt refresh token for user {user_id}, idp {idp_id}: {err}",
                "error",
                exc=err,
            )
            # Clear corrupted token
            user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                user_id, idp_id, db
            )
            return None

        # Resolve endpoints and credentials using helper methods
        token_endpoint = await self._resolve_token_endpoint(idp)
        client_id = self._decrypt_client_id(idp)
        client_secret = self._decrypt_client_secret(idp)

        # Create OAuth client for token refresh
        try:
            client = self._create_oauth_client(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=None,  # Not needed for refresh token flow
            )

            # Exchange refresh token for new tokens
            token_response = await client.fetch_token(
                token_endpoint,
                grant_type="refresh_token",
                refresh_token=refresh_token,
            )

            core_logger.print_to_log(
                f"Successfully refreshed IdP session for user {user_id}, idp {idp_id}",
                "debug",
            )

            # Store the new tokens (they may include a new refresh token)
            await self._store_idp_tokens(user_id, idp_id, token_response, db)

            return token_response

        except httpx.TimeoutException as err:
            core_logger.print_to_log(
                f"Timeout refreshing IdP session for user {user_id}, idp {idp_id}: {err}",
                "warning",
                exc=err,
            )
            # Don't clear token - IdP may be temporarily down
            return None

        except httpx.HTTPStatusError as err:
            # Check if this is a token revocation (400) or auth failure (401)
            if err.response.status_code in (400, 401):
                core_logger.print_to_log(
                    f"IdP refresh token invalid/revoked for user {user_id}, idp {idp_id}: "
                    f"{err.response.status_code} - {err.response.text}",
                    "warning",
                    exc=err,
                )
                # Clear invalid token from database
                user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                    user_id, idp_id, db
                )
                return None
            else:
                # Other HTTP errors (5xx) - don't clear token
                core_logger.print_to_log(
                    f"HTTP error refreshing IdP session for user {user_id}, idp {idp_id}: "
                    f"{err.response.status_code} - {err.response.text}",
                    "warning",
                    exc=err,
                )
                return None

        except httpx.RequestError as err:
            core_logger.print_to_log(
                f"Network error refreshing IdP session for user {user_id}, idp {idp_id}: {err}",
                "warning",
                exc=err,
            )
            # Don't clear token - network issue, not token issue
            return None

        except Exception as err:
            core_logger.print_to_log(
                f"Unexpected error refreshing IdP session for user {user_id}, idp {idp_id}: {err}",
                "error",
                exc=err,
            )
            return None

    async def revoke_idp_token(
        self,
        user_id: int,
        idp_id: int,
        db: Session,
    ) -> bool:
        """
        Attempt to revoke a refresh token at the IdP (RFC 7009).

        This method implements the OAuth2 Token Revocation specification (RFC 7009)
        to notify the IdP that a token is no longer needed. This is a best-effort
        operation - failure to revoke does not prevent local token clearing.

        Args:
            user_id (int): The ID of the user whose token should be revoked.
            idp_id (int): The ID of the identity provider.
            db (Session): The database session for token retrieval.

        Returns:
            bool: True if revocation succeeded or was not needed, False if revocation failed.

        Raises:
            Does not raise exceptions - all errors are caught and logged.

        Security Note:
            - Token revocation at the IdP provides defense in depth
            - Even if revocation fails, tokens are cleared locally
            - Network failures or unsupported IdPs return False (non-fatal)
            - Follows OAuth2 RFC 7009 specification

        RFC 7009 Specification:
            POST to revocation_endpoint with:
            - token: The refresh token to revoke
            - token_type_hint: "refresh_token" (optional)
            - client_id and client_secret for authentication

        Example:
            success = await idp_service.revoke_idp_token(user_id=123, idp_id=1, db=db)
            if success:
                # Token revoked at IdP
                clear_local_token()
            else:
                # Revocation failed (network, unsupported, etc.) but clear locally anyway
                clear_local_token()
        """
        try:
            # Get the IdP configuration
            idp = idp_crud.get_identity_provider(idp_id, db)
            if not idp or not idp.enabled:
                core_logger.print_to_log(
                    f"IdP (ID: {idp_id}) not found or disabled. Skipping token revocation.",
                    "debug",
                )
                return False

            # Get the encrypted refresh token from database
            encrypted_refresh_token = user_idp_utils.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                user_id, idp_id, db
            )

            if not encrypted_refresh_token:
                # No token to revoke - consider this success
                core_logger.print_to_log(
                    f"No refresh token to revoke for user {user_id}, idp {idp_id}",
                    "debug",
                )
                return True

            # Decrypt the refresh token
            try:
                refresh_token = core_cryptography.decrypt_token_fernet(
                    encrypted_refresh_token
                )
                if not refresh_token:
                    core_logger.print_to_log(
                        f"Failed to decrypt refresh token for revocation (user {user_id}, idp {idp_id})",
                        "warning",
                    )
                    return False
            except Exception as err:
                core_logger.print_to_log(
                    f"Error decrypting refresh token for revocation: {err}",
                    "warning",
                    exc=err,
                )
                return False

            # Try to get revocation endpoint from OIDC discovery
            revocation_endpoint = None
            if idp.issuer_url:
                try:
                    config = await self.get_oidc_configuration(idp)
                    if config:
                        revocation_endpoint = config.get("revocation_endpoint")
                except Exception as err:
                    core_logger.print_to_log(
                        f"OIDC discovery failed for revocation endpoint (IdP {idp.name}): {err}",
                        "debug",
                        exc=err,
                    )

            if not revocation_endpoint:
                # IdP doesn't advertise a revocation endpoint
                core_logger.print_to_log(
                    f"IdP {idp.name} does not support token revocation (no revocation_endpoint). "
                    "Token will be cleared locally only.",
                    "debug",
                )
                return False

            # Decrypt client secret and id for authentication
            try:
                client_id = self._decrypt_client_id(idp)
                client_secret = self._decrypt_client_secret(idp)
            except Exception as err:
                core_logger.print_to_log(
                    f"Failed to decrypt client secret or id for revocation: {err}",
                    "warning",
                    exc=err,
                )
                return False

            # Call the revocation endpoint (RFC 7009)
            try:
                client = await self._get_http_client()
                response = await client.post(
                    revocation_endpoint,
                    data={
                        "token": refresh_token,
                        "token_type_hint": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                # RFC 7009: The revocation endpoint responds with HTTP 200
                # for both successful revocations and invalid tokens
                if response.status_code == 200:
                    core_logger.print_to_log(
                        f"Successfully revoked IdP token for user {user_id}, idp {idp_id}",
                        "info",
                    )
                    return True
                else:
                    core_logger.print_to_log(
                        f"IdP revocation endpoint returned {response.status_code} for user {user_id}, idp {idp_id}",
                        "warning",
                    )
                    return False

            except httpx.TimeoutException as err:
                core_logger.print_to_log(
                    f"Timeout revoking token at IdP {idp.name} for user {user_id}: {err}",
                    "warning",
                    exc=err,
                )
                return False

            except httpx.RequestError as err:
                core_logger.print_to_log(
                    f"Network error revoking token at IdP {idp.name} for user {user_id}: {err}",
                    "warning",
                    exc=err,
                )
                return False

            except Exception as err:
                core_logger.print_to_log(
                    f"Unexpected error revoking token at IdP {idp.name} for user {user_id}: {err}",
                    "warning",
                    exc=err,
                )
                return False

        except Exception as err:
            # Catch-all for unexpected errors
            core_logger.print_to_log(
                f"Error in revoke_idp_token for user {user_id}, idp {idp_id}: {err}",
                "error",
                exc=err,
            )
            return False

    def _is_token_expired_by_age(
        self, link: user_idp_models.UsersIdentityProvider
    ) -> bool:
        """
        Check if an IdP refresh token has exceeded the maximum age policy.

        According to security best practices, refresh tokens should have a maximum lifetime
        to limit the window of exposure. This method checks if a token is older than the
        configured maximum age.

        Args:
            link (user_idp_models.UsersIdentityProvider): The user-IdP link containing token metadata.

        Returns:
            bool: True if the token exceeds maximum age, False otherwise.

        Policy:
            - Tokens older than MAX_IDP_TOKEN_AGE_DAYS are considered expired
            - Age is calculated from idp_refresh_token_updated_at (last refresh time)
            - If idp_refresh_token_updated_at is None, use linked_at (initial link time)

        Security Note:
            Enforcing maximum token age:
            - Reduces window of exposure for compromised tokens
            - Forces periodic re-authentication (validates user access)
            - Limits damage from undetected token theft
            - Complies with security frameworks (e.g., NIST 800-63B)
        """
        if not link or not link.idp_refresh_token:
            # No token stored - not expired
            return False

        now = datetime.now(timezone.utc)

        # Determine when the token was first issued or last refreshed
        token_timestamp = link.idp_refresh_token_updated_at or link.linked_at

        if not token_timestamp:
            # No timestamp available - cannot determine age (should not happen)
            core_logger.print_to_log(
                f"Warning: IdP link user_id={link.user_id}, idp_id={link.idp_id} "
                "has no timestamp for age calculation",
                "warning",
            )
            return False

        # Calculate token age (ensure timezone-aware comparison - DB stores naive UTC)
        token_timestamp_aware = token_timestamp.replace(tzinfo=timezone.utc)
        token_age = now - token_timestamp_aware

        # Check if token exceeds maximum age
        max_age = timedelta(days=MAX_IDP_TOKEN_AGE_DAYS)
        return token_age > max_age

    def _should_refresh_idp_token(
        self, link: user_idp_models.UsersIdentityProvider
    ) -> TokenAction:
        """
        Determine what action to take for an IdP token based on expiry and age policies.

        This method checks multiple conditions to decide the appropriate action:
        1. Token age - if token exceeds maximum age, it must be cleared
        2. Token existence - whether a refresh token is stored
        3. Token expiry - whether the access token is close to expiry
        4. Rate limiting - whether the token was refreshed very recently

        Args:
            link (user_idp_models.UsersIdentityProvider): The user-IdP link containing token metadata.

        Returns:
            TokenAction: The action to take (SKIP, REFRESH, or CLEAR).

        Policy:
            - CLEAR if refresh token exceeds maximum age
            - SKIP if no refresh token is stored
            - SKIP if expiry time is unknown (assume token is valid)
            - SKIP if token was refreshed in last defined time(rate limiting)
            - REFRESH if access token expires within defined minutes
            - SKIP if token is still valid and not close to expiry

        Example usage:
            link = user_idp_crud.get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
            action = self._should_refresh_idp_token(link)
            if action == TokenAction.REFRESH:
                await self.refresh_idp_session(user_id, idp_id, db)
            elif action == TokenAction.CLEAR:
                user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(user_id, idp_id, db)
        """
        # Check if refresh token exists
        if not link or not link.idp_refresh_token:
            return TokenAction.SKIP

        # Check if token has exceeded maximum age (security policy)
        if self._is_token_expired_by_age(link):
            core_logger.print_to_log(
                f"IdP refresh token for user_id={link.user_id}, idp_id={link.idp_id} "
                f"has exceeded maximum age ({MAX_IDP_TOKEN_AGE_DAYS} days). Will be cleared.",
                "info",
            )
            return TokenAction.CLEAR

        # Check if we know when the access token expires
        if not link.idp_access_token_expires_at:
            # No expiry info - assume token is still valid
            return TokenAction.SKIP

        now = datetime.now(timezone.utc)

        # Check if token was refreshed very recently (rate limiting)
        if link.idp_refresh_token_updated_at:
            # Ensure timezone-aware comparison (DB stores naive UTC datetimes)
            updated_at_aware = link.idp_refresh_token_updated_at.replace(
                tzinfo=timezone.utc
            )
            time_since_refresh = now - updated_at_aware
            if time_since_refresh < timedelta(minutes=TOKEN_REFRESH_RATE_LIMIT_MINUTES):
                # Refreshed less than defined - don't refresh again
                return TokenAction.SKIP

        # Check if access token is close to expiry
        # Ensure timezone-aware comparison (DB stores naive UTC datetimes)
        expires_at_aware = link.idp_access_token_expires_at.replace(tzinfo=timezone.utc)
        time_until_expiry = expires_at_aware - now
        if time_until_expiry < timedelta(minutes=TOKEN_EXPIRY_THRESHOLD_MINUTES):
            # Token expires soon - should refresh
            return TokenAction.REFRESH

        # Token is still valid and not close to expiry
        return TokenAction.SKIP


# Global service instance
idp_service = IdentityProviderService()
