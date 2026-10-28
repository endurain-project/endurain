"""Service layer for identity provider OAuth2/OIDC flows."""

import base64
import hashlib
import json
import secrets as secrets_module
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

import httpx2
from authlib.integrations.httpx_client import OAuth2Client
from jasil.providers import StateBackendUnavailableError, StateProvider
from joserfc import jwt
from joserfc.errors import (
    BadSignatureError,
    ExpiredTokenError,
    InvalidClaimError,
    InvalidPayloadError,
    MissingClaimError,
)
from joserfc.jwk import ECKey, OctKey, RSAKey
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.contracts as auth_identity_links_contracts
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as identity_provider_schema
import modules.auth.identity_providers.serializers as identity_provider_serializers
import modules.auth.identity_providers.utils as identity_provider_utils
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.sessions.integration_service as sessions_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


class UpstreamTimeoutError(core_exceptions.DomainError):
    """An identity provider did not answer before the request timed out."""

    status_code = 504
    code = "upstream-timeout"
    title = "Gateway Timeout"
    default_detail = "Identity provider request timed out"


# Constants for token rotation policy
MAX_IDP_TOKEN_AGE_DAYS = 90
TOKEN_EXPIRY_THRESHOLD_MINUTES = 5
TOKEN_REFRESH_RATE_LIMIT_MINUTES = 1
DEFAULT_TOKEN_EXPIRY_SECONDS = 300

# Allow-list of acceptable ID-token signature algorithms.
#
# OIDC ID tokens are verified against the IdP's *public* JWKS keys, so only
# asymmetric algorithms are valid. Pinning this list (and passing it to
# ``jwt.decode``) is mandatory defense-in-depth: without it the verifier would
# trust whatever ``alg`` the token header advertises. That would re-open two
# classic attacks — ``alg=none`` (no signature) and RS256→HS256 confusion
# (an attacker signs an HS256 token using the well-known RSA public key bytes
# as the HMAC secret). Symmetric ``HS*`` algorithms are intentionally excluded
# so a JWKS that publishes an ``oct`` key cannot be abused for key confusion.
ID_TOKEN_ALLOWED_ALGORITHMS: frozenset[str] = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "PS256",
        "PS384",
        "PS512",
        "ES256",
        "ES384",
        "ES512",
        "EdDSA",
    }
)


class TokenAction(Enum):
    """Actions to take for an IdP token based on policy evaluation.

    Attributes:
        SKIP: Token is valid, no action needed
        REFRESH: Token is close to expiry, should be refreshed
        CLEAR: Token is too old or invalid, should be cleared
    """

    SKIP = "skip"
    REFRESH = "refresh"
    CLEAR = "clear"


class IdentityProviderService:
    """Own identity-provider configuration, OAuth and token lifecycle workflows."""

    CACHE_TTL_SECONDS = 3600

    def __init__(self, state: StateProvider, frontend_host: str, api_version: str) -> None:
        """Initialize the service with shared state and entrypoint configuration."""
        self._state = state
        self._frontend_host = frontend_host
        self._api_version = api_version

    def log_public_flow_event(
        self,
        level: Literal["debug", "info", "warning", "error"],
        message: str,
        *,
        exc_info: BaseException | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Record an OAuth flow outcome detected by its transport adapter."""
        getattr(logger, level)(message, exc_info=exc_info, extra=extra)

    def create_login_oauth_state(
        self,
        idp_id: int,
        *,
        client_type: str,
        ip_address: str | None,
        redirect_path: str | None,
        code_challenge: str,
        code_challenge_method: str,
        db: Session,
    ) -> str:
        """Persist the OAuth state of a login flow and return its id.

        Args:
            idp_id: Provider the login goes through.
            client_type: ``web`` or ``mobile``.
            ip_address: Address of the client that started the flow.
            redirect_path: Frontend path to return to after login.
            code_challenge: PKCE challenge the token exchange is checked against.
            code_challenge_method: PKCE method (``S256``).
            db: Database session.

        Returns:
            The state id sent to the provider.
        """
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        oauth_state_integration.create_oauth_state(
            db=db,
            state_id=state_id,
            idp_id=idp_id,
            nonce=nonce,
            client_type=client_type,
            ip_address=ip_address,
            redirect_path=redirect_path,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )
        db.commit()
        logger.debug(
            "OAuth state created: <state_id> for IdP <idp_id> (client_type=<client_type>)",
            extra=core_logger.context(state_id=state_id, idp_id=idp_id, client_type=client_type),
        )
        return state_id

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
            extra=core_logger.context(state_id=state_id, claimed=claimed),
        )
        return claimed

    def list_identity_providers(self, db: Session) -> list[identity_provider_schema.IdentityProviderRead]:
        """List configured providers for the admin interface."""
        return [identity_provider_serializers.to_read(state) for state in idp_crud.get_all_identity_providers(db)]

    def get_identity_provider(
        self, idp_id: int, db: Session
    ) -> identity_provider_contracts.IdentityProviderState | None:
        """Return an identity-provider state by id."""
        return idp_crud.get_identity_provider(idp_id, db)

    def get_identity_provider_by_slug(
        self, slug: str, db: Session
    ) -> identity_provider_contracts.IdentityProviderState | None:
        """Return an identity-provider state by slug."""
        return idp_crud.get_identity_provider_by_slug(slug, db)

    def get_enabled_identity_providers(self, db: Session) -> list[identity_provider_schema.IdentityProviderPublicRead]:
        """Return public fields for enabled identity providers."""
        return [
            identity_provider_schema.IdentityProviderPublicRead(
                id=state.id, name=state.name, slug=state.slug, icon=state.icon
            )
            for state in idp_crud.get_enabled_identity_providers(db)
        ]

    def get_idp_templates(self) -> list[identity_provider_schema.IdentityProviderTemplateRead]:
        """Return the configured provider templates."""
        return identity_provider_utils.get_idp_templates()

    def create_identity_provider(
        self, data: identity_provider_schema.IdentityProviderCreate, db: Session
    ) -> identity_provider_schema.IdentityProviderRead:
        """Create a provider after checking its normalized slug."""
        slug = data.slug.lower()
        if idp_crud.get_identity_provider_by_slug(slug, db) is not None:
            raise core_exceptions.ConflictError(f"Identity provider with slug '{slug}' already exists")
        state = idp_crud.create_identity_provider(data, db)
        db.commit()
        logger.info("Created identity provider", extra=core_logger.context(idp_id=state.id))
        return identity_provider_serializers.to_read(state)

    def update_identity_provider(
        self,
        idp_id: int,
        data: identity_provider_schema.IdentityProviderUpdate,
        db: Session,
        *,
        if_match: str,
    ) -> identity_provider_schema.IdentityProviderRead:
        """Update a provider only when the client's version is current.

        Args:
            idp_id: Identity-provider row to update.
            data: Replacement fields.
            db: Database session.
            if_match: Version tag the client read.

        Returns:
            The updated provider.

        Raises:
            NotFoundError: When the provider is missing or removed during the update.
            PreconditionFailedError: When the provider changed since the client read it.
            ConflictError: When the new slug is already in use.
        """
        current = idp_crud.get_identity_provider(idp_id, db)
        if current is None:
            raise core_exceptions.NotFoundError("Identity provider not found")
        values = data.model_dump(exclude_unset=True)
        slug = values.get("slug")
        if slug and slug.lower() != current.slug and idp_crud.get_identity_provider_by_slug(slug.lower(), db):
            raise core_exceptions.ConflictError(f"Identity provider with slug '{slug.lower()}' already exists")
        with core_etag.refuse_stale_write(
            db,
            "identity provider",
            lambda: idp_crud.identity_provider_exists(idp_id, db),
            "Identity provider not found",
        ):
            state = idp_crud.update_identity_provider(idp_id, data, db, if_match=if_match)
            if state is None:
                raise core_exceptions.NotFoundError("Identity provider not found")
            db.commit()
        logger.info("Updated identity provider", extra=core_logger.context(idp_id=state.id))
        return identity_provider_serializers.to_read(state)

    def delete_identity_provider(self, idp_id: int, db: Session) -> None:
        """Delete an unlinked provider and commit the change."""
        if idp_crud.get_identity_provider(idp_id, db) is None:
            raise core_exceptions.NotFoundError("Identity provider not found")
        if identity_provider_links_integration.check_user_identity_providers_by_idp_id(idp_id, db):
            raise core_exceptions.ConflictError("Cannot delete identity provider with linked users")
        if not idp_crud.delete_identity_provider(idp_id, db):
            raise core_exceptions.NotFoundError("Identity provider not found")
        db.commit()
        logger.info("Deleted identity provider", extra=core_logger.context(idp_id=idp_id))

    def start_browser_link(
        self,
        link_token: str,
        idp_id: int,
        redirect: str | None,
        client_ip: str | None,
        claim_link_token: Callable[..., int],
        allowed_schemes: set[str],
        db: Session,
    ) -> str:
        """Claim a browser link token, stage OAuth state, and return the provider URL."""
        identity_provider_utils.validate_redirect_url(redirect, allowed_schemes)
        user_id = claim_link_token(link_token=link_token, idp_id=idp_id, client_ip=client_ip)
        idp = idp_crud.get_identity_provider(idp_id, db)
        if idp is None or not idp.enabled:
            raise core_exceptions.NotFoundError("Identity provider not found or disabled")
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        client_type = "mobile" if identity_provider_utils.is_custom_scheme_redirect(redirect) else "web"
        oauth_state_integration.create_oauth_state(
            db=db,
            state_id=state_id,
            idp_id=idp_id,
            nonce=nonce,
            client_type=client_type,
            ip_address=client_ip,
            user_id=user_id,
            redirect_path=redirect,
        )
        authorization_url = self.initiate_link(idp, user_id, db, oauth_state_id=state_id)
        logger.info(
            "User initiated an identity provider link", extra=core_logger.context(user_id=user_id, idp_id=idp_id)
        )
        return authorization_url

    def refresh_idp_tokens_if_needed(self, user_id: int, db: Session) -> None:
        """Refresh or clear the user's stored IdP tokens when policy requires it."""
        links = identity_provider_links_integration.get_user_identity_providers_by_user_id(user_id, db)
        for link in links:
            try:
                action = self._should_refresh_idp_token(link)
                if action is TokenAction.REFRESH:
                    self.refresh_idp_session(user_id, link.idp_id, db)
                elif action is TokenAction.CLEAR:
                    identity_provider_links_integration.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                        user_id, link.idp_id, db
                    )
            except Exception as err:
                logger.warning(
                    "Could not refresh identity-provider token",
                    exc_info=err,
                    extra=core_logger.context(user_id=user_id, idp_id=link.idp_id),
                )

    def clear_all_idp_tokens(self, user_id: int, db: Session, revoke_at_idp: bool = False) -> None:
        """Clear locally stored IdP tokens, optionally revoking them remotely."""
        links = identity_provider_links_integration.get_user_identity_providers_by_user_id(user_id, db)
        for link in links:
            try:
                if revoke_at_idp:
                    try:
                        self.revoke_idp_token(user_id, link.idp_id, db)
                    except Exception as err:
                        logger.warning(
                            "Could not revoke identity-provider token during logout",
                            exc_info=err,
                            extra=core_logger.context(user_id=user_id, idp_id=link.idp_id),
                        )
                identity_provider_links_integration.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                    user_id, link.idp_id, db
                )
            except Exception as err:
                logger.warning(
                    "Could not clear identity-provider token during logout",
                    exc_info=err,
                    extra=core_logger.context(user_id=user_id, idp_id=link.idp_id),
                )

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
    def _http_client(self) -> Iterator[httpx2.Client]:
        """Open a short-lived HTTP client for one outbound request."""
        with httpx2.Client(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": f"Endurain/{self._api_version} (OIDC Client)", "Accept": "application/json"},
        ) as client:
            yield client

    def _fetch_jwks(self, jwks_uri: str) -> dict[str, Any]:
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
            with self._http_client() as client:
                response = client.get(jwks_uri)
            response.raise_for_status()

            jwks = response.json()

            # Validate JWKS structure
            if not isinstance(jwks, dict) or "keys" not in jwks:
                logger.error(
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
            logger.error(
                "Timeout fetching JWKS from <jwks_uri>: <err>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, err=err),
            )
            raise UpstreamTimeoutError("Timeout retrieving signing keys from identity provider") from err
        except httpx2.HTTPStatusError as err:
            logger.error(
                "HTTP error fetching JWKS from <jwks_uri>: <status_code>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, status_code=err.response.status_code),
            )
            raise core_exceptions.UpstreamError(
                f"Identity provider JWKS endpoint returned error: {err.response.status_code}"
            ) from err
        except json.JSONDecodeError as err:
            logger.error(
                "Invalid JSON in JWKS response from <jwks_uri>: <err>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, err=err),
            )
            raise core_exceptions.UpstreamError("Identity provider returned invalid JWKS JSON") from err
        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.error(
                "Unexpected error fetching JWKS from <jwks_uri>: <err>",
                exc_info=err,
                extra=core_logger.context(jwks_uri=jwks_uri, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to retrieve signing keys from identity provider") from err

    def _verify_id_token(
        self,
        id_token: str,
        jwks_uri: str,
        expected_issuer: str,
        expected_audience: str,
        expected_nonce: str | None = None,
    ) -> dict[str, Any]:
        """Verifies the ID token's signature and claims using JWKS from the identity provider.

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
            domain error: If verification fails (invalid signature, expired token, claim mismatch)

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
                logger.warning(
                    "Invalid JWT format: expected 3 parts, got <value_1>", extra=core_logger.context(value_1=len(parts))
                )
                raise core_exceptions.UnauthenticatedError("Invalid ID token format")

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
                logger.warning("ID token header missing 'kid' claim")
                raise core_exceptions.UnauthenticatedError("ID token missing key identifier")

            if not alg:
                logger.warning("ID token header missing 'alg' claim")
                raise core_exceptions.UnauthenticatedError("ID token missing algorithm")

            # Reject disallowed algorithms before importing the key.
            # This blocks ``alg=none`` and symmetric ``HS*`` algorithms,
            # which would otherwise enable signature-bypass and RS256→HS256
            # key-confusion attacks against the public JWKS keys.
            if alg not in ID_TOKEN_ALLOWED_ALGORITHMS:
                logger.warning("ID token uses disallowed algorithm: <alg>", extra=core_logger.context(alg=alg))
                raise core_exceptions.UnauthenticatedError("ID token uses an unsupported signature algorithm")

            logger.debug("ID token header: kid=<kid>, alg=<alg>", extra=core_logger.context(kid=kid, alg=alg))

            # Step 2: Fetch JWKS from IdP
            jwks = self._fetch_jwks(jwks_uri)

            # Step 3: Find the matching key in JWKS
            matching_key = None
            for key_data in jwks.get("keys", []):
                if key_data.get("kid") == kid:
                    matching_key = key_data
                    break

            if not matching_key:
                logger.warning("No matching key found in JWKS for kid=<kid>", extra=core_logger.context(kid=kid))
                raise core_exceptions.UnauthenticatedError("ID token signed with unknown key")

            logger.debug(
                "Found matching key in JWKS: kid=<kid>, kty=<value_2>",
                extra=core_logger.context(kid=kid, value_2=matching_key.get("kty")),
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
                logger.warning("Unsupported key type in JWKS: <key_type>", extra=core_logger.context(key_type=key_type))
                raise core_exceptions.UnauthenticatedError(f"Unsupported key type: {key_type}")

            # Step 5: Verify signature and decode claims
            # joserfc will verify the signature using the public key.
            # The ``algorithms`` allow-list is mandatory: it pins the
            # acceptable signature algorithms so a forged ``alg`` header
            # (``none`` or a symmetric ``HS*`` confusion attack) cannot
            # bypass verification, mirroring TokenManager.decode_token.
            decoded = jwt.decode(
                id_token,
                key,
                algorithms=list(ID_TOKEN_ALLOWED_ALGORITHMS),
            )
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

            logger.debug(
                "Successfully verified ID token signature for sub=<value_1>",
                extra=core_logger.context(value_1=claims.get("sub")),
            )

            # Step 6: Validate nonce if provided
            # The nonce is used to prevent replay attacks in OAuth2/OIDC flows
            if expected_nonce:
                token_nonce = claims.get("nonce")
                if not token_nonce:
                    logger.warning("ID token missing nonce claim but nonce was expected")
                    raise core_exceptions.UnauthenticatedError("ID token missing nonce")

                if token_nonce != expected_nonce:
                    logger.warning(
                        "ID token nonce mismatch: expected <expected_nonce>, got <token_nonce>",
                        extra=core_logger.context(expected_nonce=expected_nonce, token_nonce=token_nonce),
                    )
                    raise core_exceptions.UnauthenticatedError("ID token nonce mismatch")

            # Return verified claims
            return claims

        except BadSignatureError as err:
            logger.warning(
                "ID token signature verification failed: <err>", exc_info=err, extra=core_logger.context(err=err)
            )
            raise core_exceptions.UnauthenticatedError("ID token signature is invalid") from err
        except ExpiredTokenError as err:
            logger.warning("ID token has expired: <err>", exc_info=err, extra=core_logger.context(err=err))
            raise core_exceptions.UnauthenticatedError("ID token has expired") from err
        except InvalidClaimError as err:
            logger.warning("ID token claim validation failed: <err>", exc_info=err, extra=core_logger.context(err=err))
            raise core_exceptions.UnauthenticatedError(f"ID token claim validation failed: {err}") from err
        except MissingClaimError as err:
            logger.warning("ID token missing required claim: <err>", exc_info=err, extra=core_logger.context(err=err))
            raise core_exceptions.UnauthenticatedError(f"ID token missing required claim: {err}") from err
        except InvalidPayloadError as err:
            logger.warning("ID token payload is invalid: <err>", exc_info=err, extra=core_logger.context(err=err))
            raise core_exceptions.UnauthenticatedError("ID token payload is invalid") from err
        except core_exceptions.DomainError:
            # Re-raise domain errors from _fetch_jwks or our own validations
            raise
        except Exception as err:
            logger.error("Unexpected error verifying ID token: <err>", exc_info=err, extra=core_logger.context(err=err))
            raise core_exceptions.ProcessingError("Failed to verify ID token") from err

    def get_oidc_configuration(self, idp: identity_provider_contracts.IdentityProviderState) -> dict[str, Any] | None:
        """Retrieves the OpenID Connect (OIDC) discovery configuration for a given identity provider.

        This method attempts to fetch the OIDC configuration from the provider's well-known discovery endpoint.
        It uses an in-memory cache to avoid redundant network requests and respects a cache TTL (time-to-live).
        If the configuration is cached and not expired, it is returned directly from the cache.
        Otherwise, it fetches the configuration over HTTP, caches it, and returns the result.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing the issuer URL and unique ID.

        Returns:
            dict[str, Any] | None: The OIDC discovery configuration as a dictionary if successful, or None if fetching fails
            or the issuer URL is not provided.

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
            with self._http_client() as client:
                response = client.get(discovery_url)

            response.raise_for_status()
            config = response.json()

            self._write_cache(self._discovery_key(idp.id), config)

            return config
        except httpx2.HTTPStatusError as err:
            logger.warning(
                "HTTP error fetching OIDC discovery for <name>: <status_code> - <text>",
                extra=core_logger.context(name=idp.name, status_code=err.response.status_code, text=err.response.text),
            )
            return None
        except httpx2.ConnectError as err:
            logger.error(
                "Connection error fetching OIDC discovery for <name>. URL: <discovery_url>. Error: <err>. Check if the service is reachable and not using 'localhost' in Docker.",
                extra=core_logger.context(name=idp.name, discovery_url=discovery_url, err=err),
            )
            return None
        except httpx2.RequestError as err:
            logger.warning(
                "Request error fetching OIDC discovery for <name>. URL: <discovery_url>. Error: <err>",
                extra=core_logger.context(name=idp.name, discovery_url=discovery_url, err=err),
            )
            return None
        except core_exceptions.DomainError as err:
            if err.status_code == 400:
                # The SSRF guard refused the URL. Log with an actionable
                # hint for the operator so they know about the
                # SSRF_ALLOWED_HOSTS escape hatch for self-hosted IdPs.
                logger.warning(
                    "OIDC discovery for <name> was rejected: <detail>. URL: <discovery_url>. If this is a self-hosted IdP on a private network, add its host or CIDR to SSRF_ALLOWED_HOSTS.",
                    extra=core_logger.context(name=idp.name, detail=err.detail, discovery_url=discovery_url),
                )
            else:
                # The hostname could not be checked (resolution timed out or the
                # lookup pool is busy). The URL was not judged, so no hint.
                logger.warning(
                    "OIDC discovery for <name> could not be checked: <detail>. URL: <discovery_url>.",
                    extra=core_logger.context(name=idp.name, detail=err.detail, discovery_url=discovery_url),
                )
            return None
        except Exception as err:
            if hasattr(err, "status_code") and hasattr(err, "detail"):
                if err.status_code == 400:
                    logger.warning(
                        "OIDC discovery for <name> was rejected: <detail>. URL: <discovery_url>. If this is a self-hosted IdP on a private network, add its host or CIDR to SSRF_ALLOWED_HOSTS.",
                        extra=core_logger.context(name=idp.name, detail=err.detail, discovery_url=discovery_url),
                    )
                else:
                    logger.warning(
                        "OIDC discovery for <name> could not be checked: <detail>. URL: <discovery_url>.",
                        extra=core_logger.context(name=idp.name, detail=err.detail, discovery_url=discovery_url),
                    )
                return None
            logger.warning(
                "Failed to fetch OIDC discovery for <name>: <err>", extra=core_logger.context(name=idp.name, err=err)
            )
            return None

    def _get_redirect_uri(self, idp_slug: str) -> str:
        """Generates the redirect URI for a given identity provider slug.

        Args:
            idp_slug (str): The slug identifier for the identity provider.

        Returns:
            str: The complete redirect URI for the specified identity provider.
        """
        base_url = self._frontend_host
        return f"{base_url}/api/v1/public/idp/callback/{idp_slug}"

    def _decrypt_client_id(self, idp: identity_provider_contracts.IdentityProviderState) -> str:
        """Decrypts the client ID of the given identity provider.

        Attempts to decrypt the `client_id` attribute of the provided `IdentityProvider` instance
        using Fernet symmetric encryption. If decryption fails or returns an empty value, logs the error
        and raises an HTTP 500 exception indicating a configuration error.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing the encrypted client ID.

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
            logger.error(
                "Failed to decrypt client ID for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError(
                f"Identity provider {idp.name} configuration error. Please contact administrator."
            ) from err

    def _decrypt_client_secret(self, idp: identity_provider_contracts.IdentityProviderState) -> str:
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
            logger.error(
                "Failed to decrypt client secret for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError(
                f"Identity provider {idp.name} configuration error. Please contact administrator."
            ) from err

    def _resolve_token_endpoint(self, idp: identity_provider_contracts.IdentityProviderState) -> str:
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

    def _create_oauth_client(
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
            follow_redirects=True,
            headers={"User-Agent": f"Endurain/{self._api_version} (OIDC Client)", "Accept": "application/json"},
        )

    def initiate_login(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        db: Session,
        redirect_path: str | None = None,
        oauth_state_id: str | None = None,
    ) -> str:
        """Initiates the OAuth2/OIDC login process for the given identity provider.

        This method prepares the authorization URL for the user to authenticate with the specified
        identity provider (IdP). It handles endpoint discovery and authorization URL construction.


        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing configuration details.
            request (Request): The current HTTP request object.
            db (Session): The database session.
            redirect_path (str | None): Optional frontend path to redirect to after successful login.
            oauth_state_id (str | None): Database OAuth state ID (from PKCE flow).

        Returns:
            str: The authorization URL to which the user should be redirected to initiate login.

        Raises:
            domain error: If the identity provider is not properly configured or if an error occurs during initiation.
        """
        try:
            client_id = self._decrypt_client_id(idp)

            # Get endpoints
            authorization_endpoint = idp.authorization_endpoint

            # Try OIDC discovery if issuer URL is provided
            if not authorization_endpoint and idp.issuer_url:
                config = self.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise core_exceptions.UpstreamError(
                    f"Identity provider {idp.name} authorization "
                    "endpoint could not be resolved. Verify the "
                    "issuer URL is reachable; if it is on a "
                    "private network, add its host or CIDR to "
                    "SSRF_ALLOWED_HOSTS."
                )

            # Retrieve database-backed OAuth state (mandatory for all clients)
            if not oauth_state_id:
                raise core_exceptions.ProcessingError("OAuth state ID is required (PKCE mandatory)")

            oauth_state_obj = oauth_state_integration.get_oauth_state_by_id_and_not_used(oauth_state_id, db)
            if not oauth_state_obj:
                raise core_exceptions.ProcessingError("OAuth state not found")

            state = oauth_state_id
            nonce = oauth_state_obj.nonce

            # Build authorization URL
            redirect_uri = self._get_redirect_uri(idp.slug)
            scopes = idp.scopes or "openid profile email"

            with OAuth2Client(client_id=client_id, redirect_uri=redirect_uri, scope=scopes) as client:
                authorization_url, _ = client.create_authorization_url(authorization_endpoint, state=state, nonce=nonce)

            return authorization_url

        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.error(
                "Error initiating OAuth login for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to initiate SSO login") from err

    def initiate_link(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        user_id: int,
        db: Session,
        oauth_state_id: str | None = None,
    ) -> str:
        """Initiates the OAuth/OIDC authorization flow for linking an identity provider to an existing user account.

        This method generates the authorization URL that redirects the user to the identity provider's
        login page. Uses database-backed OAuth state for security and replay protection.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider configuration object containing
                client credentials, endpoints, and other OAuth/OIDC settings.
            request (Request): The FastAPI request object used to access and store session data.
            user_id (int): The ID of the authenticated user who is linking their account to the
                identity provider.
            db (Session): The database session for database operations.
            oauth_state_id (str | None): Database OAuth state ID (required for secure linking).

        Returns:
            str: The authorization URL to redirect the user to for identity provider authentication.

        Raises:
            domain error:
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
                config = self.get_oidc_configuration(idp)
                if config:
                    authorization_endpoint = config.get("authorization_endpoint")

            if not authorization_endpoint:
                raise core_exceptions.UpstreamError(
                    f"Identity provider {idp.name} authorization "
                    "endpoint could not be resolved. Verify the "
                    "issuer URL is reachable; if it is on a "
                    "private network, add its host or CIDR to "
                    "SSRF_ALLOWED_HOSTS."
                )

            # Retrieve database-backed OAuth state (required for link mode)
            if not oauth_state_id:
                raise core_exceptions.ProcessingError("OAuth state ID is required for secure linking")

            oauth_state_obj = oauth_state_integration.get_oauth_state_by_id_and_not_used(oauth_state_id, db)
            if not oauth_state_obj:
                raise core_exceptions.ProcessingError("OAuth state not found")

            # Validate user_id matches (security check for link mode)
            if oauth_state_obj.user_id != user_id:
                raise core_exceptions.ProcessingError("OAuth state user mismatch")

            state = oauth_state_id
            nonce = oauth_state_obj.nonce

            # Build authorization URL
            redirect_uri = self._get_redirect_uri(idp.slug)
            scopes = idp.scopes or "openid profile email"

            with OAuth2Client(client_id=client_id, redirect_uri=redirect_uri, scope=scopes) as client:
                authorization_url, _ = client.create_authorization_url(authorization_endpoint, state=state, nonce=nonce)

            return authorization_url

        except core_exceptions.DomainError:
            raise
        except Exception as err:
            logger.error(
                "Error initiating OAuth link for IdP <name>, user <user_id>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, user_id=user_id, err=err),
            )
            raise core_exceptions.ProcessingError("Failed to initiate identity provider linking") from err

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
            client_id = self._decrypt_client_id(idp)
            client_secret = self._decrypt_client_secret(idp)
            token_endpoint = self._resolve_token_endpoint(idp)

            # Get OIDC configuration (for userinfo, jwks_uri, issuer)
            userinfo_endpoint = idp.userinfo_endpoint
            jwks_uri = None
            expected_issuer = None

            if idp.issuer_url:
                try:
                    config = self.get_oidc_configuration(idp)
                    if config:
                        # Get userinfo endpoint if not manually configured
                        if not userinfo_endpoint:
                            userinfo_endpoint = config.get("userinfo_endpoint")

                        # Get JWKS URI for ID token verification
                        jwks_uri = config.get("jwks_uri")
                        expected_issuer = config.get("issuer")

                        logger.debug(
                            "OIDC discovery complete for <name>: userinfo=<value_2>, jwks_uri=<value_3>, issuer=<value_4>",
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
            redirect_uri = self._get_redirect_uri(idp.slug)

            try:
                oauth_client = self._create_oauth_client(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri=redirect_uri,
                )

                token_response = oauth_client.fetch_token(token_endpoint, grant_type="authorization_code", code=code)
            except httpx2.TimeoutException as err:
                logger.error(
                    "Timeout connecting to IdP <name> token endpoint: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, err=err),
                )
                raise UpstreamTimeoutError(
                    f"Identity provider {idp.name} is not responding. Please try again later."
                ) from err
            except httpx2.HTTPStatusError as err:
                logger.error(
                    "HTTP error from IdP <name> token endpoint: <status_code> - <text>",
                    exc_info=err,
                    extra=core_logger.context(
                        name=idp.name, status_code=err.response.status_code, text=err.response.text
                    ),
                )
                # Check for common OAuth2 error responses
                if err.response.status_code == 400:
                    detail = "Authorization code is invalid or expired. Please try logging in again."
                elif err.response.status_code == 401:
                    detail = f"Identity provider {idp.name} rejected the authentication request. Please contact administrator."
                else:
                    detail = f"Identity provider {idp.name} returned an error. Please try again later."

                raise core_exceptions.UpstreamError(detail) from err
            except httpx2.RequestError as err:
                logger.error(
                    "Network error connecting to IdP <name>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, err=err),
                )
                raise core_exceptions.UpstreamError(
                    f"Unable to connect to identity provider {idp.name}. Please check your network connection."
                ) from err
            except Exception as err:
                logger.error(
                    "Unexpected error during token exchange with IdP <name>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, err=err),
                )
                raise core_exceptions.ProcessingError("Failed to complete authentication. Please try again.") from err

                # Get user information with ID token verification
                userinfo = self._get_userinfo(
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
                logger.error(
                    "IdP <name> did not provide 'sub' or 'id' claim in userinfo: <value_2>",
                    extra=core_logger.context(name=idp.name, value_2=list(userinfo.keys())),
                )
                raise core_exceptions.UpstreamError(
                    f"Identity provider {idp.name} did not provide required user identifier. Please contact administrator."
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
                    user = self._update_user_from_idp(user, idp, userinfo, db)

                # Store IdP tokens for future use
                self._store_idp_tokens(link_user_id, idp.id, token_response, db)

                logger.info(
                    "User <username> (id=<link_user_id>) linked IdP <name> (subject=<subject>)",
                    extra=core_logger.context(
                        username=user.username, link_user_id=link_user_id, name=idp.name, subject=subject
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
                user = self._find_or_create_user(idp, subject, userinfo, password_hasher, db)

                # Store IdP tokens for future session renewal
                self._store_idp_tokens(user.id, idp.id, token_response, db)

                db.commit()
                logger.info(
                    "User <username> authenticated via IdP <name>",
                    extra=core_logger.context(username=user.username, name=idp.name),
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
            logger.error(
                "Unexpected error handling OAuth callback for IdP <name>: <err>",
                exc_info=err,
                extra=core_logger.context(name=idp.name, err=err),
            )
            raise core_exceptions.ProcessingError(
                f"An unexpected error occurred during authentication with {idp.name}. Please try again or contact administrator."
            ) from err
        finally:
            if oauth_client is not None:
                oauth_client.close()

    def create_callback_session(
        self,
        user: Any,
        request: Any,
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
            request,
            None,
            password_hasher,
            expires_at,
            db,
            oauth_state_id=oauth_state_id,
        )
        db.commit()
        logger.debug("SSO callback session created", extra=core_logger.context(user_id=user_read.id))
        return session_id

    def _get_userinfo(
        self,
        token_response: dict[str, Any],
        userinfo_endpoint: str | None,
        client: OAuth2Client,
        jwks_uri: str | None,
        expected_issuer: str | None,
        expected_audience: str,
        expected_nonce: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve user information from an identity provider using the provided token response.

        This method first attempts to fetch user information from the given `userinfo_endpoint` using the provided OAuth2 client.
        If the endpoint is unavailable or the request fails, it falls back to extracting claims from the `id_token` in the token response,
        verifying the ID token signature using JWKS before returning the claims.

        Security Enhancement:
        - ID tokens are now cryptographically verified using joserfc and JWKS
        - Signature verification prevents token forgery and tampering
        - Claims validation ensures token integrity (iss, aud, exp, nonce)
        - This replaces the insecure manual base64 decode previously used

        Args:
            token_response (dict[str, Any]): The OAuth2 token response containing access and/or ID tokens.
            userinfo_endpoint (str | None): The endpoint URL to fetch user information, if available.
            client (OAuth2Client): The asynchronous OAuth2 client used to make HTTP requests.
            jwks_uri (str | None): The JWKS endpoint URL for verifying ID token signatures.
            expected_issuer (str | None): Expected 'iss' claim value from OIDC discovery.
            expected_audience (str): Expected 'aud' claim value (typically the client_id).
            expected_nonce (str | None): Expected nonce value from session (optional, but recommended).

        Returns:
            dict[str, Any]: The user information claims retrieved from the identity provider.

        Raises:
            domain error: If user information cannot be retrieved from either the userinfo endpoint or the ID token,
                          or if ID token verification fails.
        """
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
                    "HTTP error <status_code> fetching userinfo: <text>",
                    exc_info=err,
                    extra=core_logger.context(status_code=err.response.status_code, text=err.response.text),
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
                id_token_claims = self._verify_id_token(
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
                    # Merge: userinfo endpoint data + ID token verified claims
                    # ID token claims override for security-critical fields
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
                logger.error(
                    "Unexpected error verifying ID token: <err>", exc_info=err, extra=core_logger.context(err=err)
                )
                raise core_exceptions.ProcessingError("Failed to verify ID token") from err

        # If we got userinfo from endpoint but no ID token, return userinfo
        if userinfo_claims:
            return userinfo_claims

        # If ID token exists but we're missing JWKS/issuer info, log warning
        if id_token and (not jwks_uri or not expected_issuer):
            logger.warning(
                "ID token present but cannot verify: missing JWKS URI or issuer. "
                "Configure issuer_url for OIDC discovery."
            )

        # If we get here, we couldn't retrieve or verify any user information
        logger.error("Failed to retrieve user information from userinfo endpoint or ID token")
        raise core_exceptions.ProcessingError(
            "Unable to retrieve user information from identity provider. Please contact administrator."
        )

    def _store_idp_tokens(
        self,
        user_id: int,
        idp_id: int,
        token_response: dict[str, Any],
        db: Session,
    ) -> None:
        """Store IdP tokens after successful authentication.

        This method extracts the refresh token from the OAuth token response, encrypts it,
        and stores it along with metadata for future session renewal. If no refresh token
        is provided by the IdP, the method logs a debug message and returns gracefully.

        Args:
            user_id (int): The ID of the authenticated user.
            idp_id (int): The ID of the identity provider.
            token_response (dict[str, Any]): The OAuth token response from the IdP containing
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
            logger.debug(
                "No refresh token provided by IdP (user_id=<user_id>, idp_id=<idp_id>). User will need to re-authenticate when session expires.",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return

        try:
            # Encrypt the refresh token using Fernet
            encrypted_refresh = core_cryptography.encrypt_token_fernet(refresh_token)

            if not encrypted_refresh:
                logger.warning(
                    "Failed to encrypt refresh token for user <user_id>, idp <idp_id>. Token will not be stored.",
                    extra=core_logger.context(user_id=user_id, idp_id=idp_id),
                )
                return

            # Calculate when the access token expires
            expires_in = token_response.get("expires_in", DEFAULT_TOKEN_EXPIRY_SECONDS)
            access_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            # Store encrypted token and metadata in database
            identity_provider_links_integration.store_user_identity_provider_tokens(
                user_id=user_id,
                idp_id=idp_id,
                encrypted_refresh_token=encrypted_refresh,
                access_token_expires_at=access_token_expires_at,
                db=db,
            )

            logger.debug(
                "Stored IdP refresh token for user <user_id>, idp <idp_id> (expires at <value_3>)",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, value_3=access_token_expires_at.isoformat()),
            )

        except Exception as err:
            # Log the error but don't fail the authentication flow
            logger.error(
                "Error storing IdP refresh token for user <user_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, err=err),
            )
            # Authentication succeeds even if token storage fails
            # User will need to re-auth when session expires, but that's acceptable

    def _map_user_claims(
        self, idp: identity_provider_contracts.IdentityProviderState, claims: dict[str, Any]
    ) -> dict[str, Any]:
        """Maps user claims from an identity provider to a standardized user dictionary.

        This method takes an identity provider configuration and a dictionary of claims,
        then maps the claims to standard user fields (such as 'username', 'email', and 'name')
        using both default and custom mappings defined in the identity provider.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing optional custom user mapping.
            claims (dict[str, Any]): The dictionary of claims received from the identity provider.

        Returns:
            dict[str, Any]: A dictionary mapping standard user fields to their corresponding claim values.
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
                if claims.get(claim):
                    result[field] = claims[claim]
                    break

        return result

    @staticmethod
    def _is_email_verified(claims: dict[str, Any]) -> bool:
        """Return ``True`` only when the IdP asserts a verified email.

        Honors the standard OIDC ``email_verified`` claim. Providers may
        send it as a JSON boolean (``true``) or, less correctly, as the
        string ``"true"``; both are accepted. Any other value — including
        a missing claim — is treated as *unverified* so that email-based
        account linking fails closed.

        Args:
            claims: Raw userinfo/ID-token claims from the identity provider.

        Returns:
            ``True`` if the email is explicitly asserted as verified.
        """
        value = claims.get("email_verified")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return False

    def _find_or_create_user(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        subject: str,
        userinfo: dict[str, Any],
        password_hasher: credentials_integration.PasswordHasher,
        db: Session,
    ) -> users_schema.UsersRead:
        """Finds an existing user linked to the given identity provider and subject, or creates a new user if allowed.

        This method attempts to:
        1. Find a user by their identity provider (IdP) link using the subject identifier.
        2. If not found, find a user by email and link their account to the IdP,
           but only when the IdP asserts the email is verified (account-takeover
           prevention via the OIDC ``email_verified`` claim).
        3. If still not found and auto-creation is enabled, create a new user from the IdP information.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            userinfo (Dict[str, Any]): User information/claims from the IdP.
            password_hasher (credentials_integration.PasswordHasher): The password hasher instance.
            db (Session): Database session.

        Returns:
            users_schema.UsersRead: The found or newly created user instance.

        Raises:
            domain error: If an existing account matches the email but the IdP
                did not assert a verified email (403), or if user creation is
                disabled for the identity provider and no existing user is found.
        """
        # Try to find existing user by IdP link
        link = identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id(idp.id, subject, db)

        if link:
            # Fetch the linked user through the CRUD layer so we work with
            # the UsersRead schema rather than reaching into the ORM
            # relationship (link.users) and crossing the module boundary.
            user = users_integration.get_user(link.user_id, db)
            if user is None:
                raise core_exceptions.NotFoundError("User not found")
            # Update last login timestamp
            identity_provider_links_integration.update_user_identity_provider_last_login(link.user_id, idp.id, db)

            # Update user info if sync is enabled
            if idp.sync_user_info:
                user = self._update_user_from_idp(user, idp, userinfo, db)
            return user

        # Try to find by email (for linking existing accounts).
        #
        # SECURITY (account-takeover prevention): only auto-link an
        # external identity to an EXISTING local account when the IdP
        # asserts that the email is verified (standard OIDC
        # ``email_verified`` claim). Without this gate, an attacker who
        # registers an unverified address matching a victim's email at a
        # permissive IdP would be auto-linked into — and gain control of —
        # the victim's existing account on first SSO login. Subject-based
        # linking above is unaffected; this only guards the email fallback.
        mapped_data = self._map_user_claims(idp, userinfo)
        email = mapped_data.get("email")

        if email:
            user = users_integration.get_user_by_email(email, db)
            if user:
                if not self._is_email_verified(userinfo):
                    logger.warning(
                        "Refusing to link IdP <name> to existing account <username>: provider did not assert a verified email",
                        extra=core_logger.context(name=idp.name, username=user.username),
                    )
                    raise core_exceptions.PermissionDeniedError(
                        "Cannot link this identity provider to an existing "
                        "account because the provider did not verify the "
                        "email address."
                    )

                # Link existing account to IdP
                identity_provider_links_integration.create_user_identity_provider(user.id, idp.id, subject, db)

                logger.info(
                    "Linked existing user <username> to IdP <name>",
                    extra=core_logger.context(username=user.username, name=idp.name),
                )

                # Update user info if sync is enabled
                if idp.sync_user_info:
                    user = self._update_user_from_idp(user, idp, userinfo, db)
                return user

        # Create new user if auto-creation is enabled
        if not idp.auto_create_users:
            raise core_exceptions.PermissionDeniedError("User account creation is disabled for this identity provider")

        user = self._create_user_from_idp(idp, subject, mapped_data, password_hasher, db)

        return user

    def _create_user_from_idp(
        self,
        idp: identity_provider_contracts.IdentityProviderState,
        subject: str,
        mapped_data: dict[str, Any],
        password_hasher: credentials_integration.PasswordHasher,
        db: Session,
    ) -> users_schema.UsersRead:
        """Creates a new user in the database based on identity provider (IdP) information.

        This method generates a unique username, creates a user with mapped data from the IdP
        using the existing CRUD layer, and links the user to the IdP subject. SSO accounts get
        no local password credential — ``create_signup_user`` is called with
        ``persist_credential=False`` so no row is written to ``users_local_credentials`` and
        ``has_local_password`` correctly reports ``False``. The user's email is marked as
        verified since we trust the IdP's verification.

        Args:
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance.
            subject (str): The unique subject identifier from the IdP.
            mapped_data (Dict[str, Any]): User data mapped from the IdP (e.g., username, email, name).
            password_hasher (credentials_integration.PasswordHasher): The password hasher instance.
            db (Session): The database session.

        Returns:
            users_schema.UsersRead: The newly created user instance.

        Raises:
            domain error: If user creation fails (e.g., duplicate username/email).
        """
        # Generate a random password solely to satisfy the required
        # UsersSignup.password field. It is never validated, hashed, or
        # stored because the user is created with persist_credential=False
        # (SSO accounts have no local credential row).
        random_password = password_hasher.generate_password(length=16)

        # Ensure username is unique
        base_username = mapped_data.get("username", f"user_{subject[:8]}")
        username = base_username
        while users_integration.get_user_by_username(username, db):
            # secrets.randbelow is a CSPRNG; generate a 6-digit suffix
            username = f"{base_username}_{secrets_module.randbelow(900000) + 100000}"

        # Create user signup schema
        user_signup = users_schema.UsersSignup(
            username=username,
            email=mapped_data.get("email", f"{username}@sso.local"),
            city=mapped_data.get("city"),
            birthdate=mapped_data.get("birthdate"),
            name=mapped_data.get("name", username),
            password=random_password,
            preferred_language=users_schema.Language.ENGLISH,
            gender=users_schema.Gender.UNSPECIFIED,
            units=server_settings_schema.Units.METRIC,
            height=mapped_data.get("height"),
            max_heart_rate=mapped_data.get("max_heart_rate"),
            first_day_of_week=users_schema.WeekDay.MONDAY,
            currency=server_settings_schema.Currency.EURO,
        )

        server_settings = server_settings_integration.get_server_settings(db)

        created_user = users_integration.create_sso_user(user_signup, server_settings, db)

        # Create the IdP link
        identity_provider_links_integration.create_user_identity_provider(created_user.id, idp.id, subject, db)

        logger.info(
            "Created new user <username> from IdP <name>",
            extra=core_logger.context(username=created_user.username, name=idp.name),
        )

        return created_user

    def _update_user_from_idp(
        self,
        user: users_schema.UsersRead,
        idp: identity_provider_contracts.IdentityProviderState,
        userinfo: dict[str, Any],
        db: Session,
    ) -> users_schema.UsersRead:
        """Updates the user's information based on claims received from an identity provider (IdP).

        This method syncs user profile information from the IdP to the local user account when
        IdP sync is enabled. It performs the following steps:
        1. Maps claims from IdP userinfo to standard user fields (email, name)
        2. Validates email changes - checks if new email is already in use by another user
        3. Skips email updates if conflict detected and logs the issue
        4. Builds an updated copy of the user schema with the changed fields
        5. Delegates persistence to the CRUD layer (edit_user)

        Args:
            user (users_schema.UsersRead): The user schema instance to update.
            idp (identity_provider_contracts.IdentityProviderState): The identity provider instance with user_mapping config.
            userinfo (Dict[str, Any]): The user information claims received from the IdP.
            db (Session): The SQLAlchemy database session.

        Returns:
            users_schema.UsersRead: The updated user schema instance from database.
        """
        mapped_data = self._map_user_claims(idp, userinfo)

        # Build updates
        updates = {}

        # Check email - verify not already in use
        if "email" in mapped_data and mapped_data["email"] != user.email:
            existing_user = users_integration.get_user_by_email(mapped_data["email"], db)
            if existing_user and existing_user.id != user.id:
                logger.warning(
                    "Cannot sync email from IdP <name>: <value_2> already in use by another user",
                    extra=core_logger.context(name=idp.name, value_2=mapped_data["email"]),
                )
            else:
                logger.debug(
                    "Syncing email for user <username> from IdP <name>: <email> -> <value_4>",
                    extra=core_logger.context(
                        username=user.username, name=idp.name, email=user.email, value_4=mapped_data["email"]
                    ),
                )
                updates["email"] = mapped_data["email"].strip()

        # Check name
        if "name" in mapped_data and mapped_data["name"] != user.name:
            logger.debug(
                "Syncing name for user <username> from IdP <name>: <name_2> -> <value_4>",
                extra=core_logger.context(
                    username=user.username, name=idp.name, name_2=user.name, value_4=mapped_data["name"]
                ),
            )
            updates["name"] = mapped_data["name"].strip()

        # Only call CRUD if there are updates
        if updates:
            logger.info(
                "Applying updates to user <username>: <updates>",
                extra=dict(
                    {
                        **core_logger.context(),
                        **core_logger.context(username=user.username, updates=updates),
                    }
                ),
            )
            updated_user = user.model_copy(update=updates)
            user = users_integration.edit_user(
                user.id, users_schema.UsersEdit.from_read(updated_user), db, if_match="*"
            )
            db.commit()

        return user

    def refresh_idp_session(
        self,
        user_id: int,
        idp_id: int,
        db: Session,
    ) -> dict[str, Any] | None:
        """Attempt to refresh a user's IdP session using stored refresh token.

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
            domain error: If the IdP is not found, disabled, or misconfigured.

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
            raise core_exceptions.NotFoundError(f"Identity provider (ID: {idp_id}) not found or disabled")

        # Get the encrypted refresh token from database
        encrypted_refresh_token = (
            identity_provider_links_integration.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                user_id, idp_id, db
            )
        )

        if not encrypted_refresh_token:
            logger.debug(
                "No refresh token stored for user <user_id>, idp <idp_id>. Cannot refresh session.",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return None

        # Decrypt the refresh token
        try:
            refresh_token = core_cryptography.decrypt_token_fernet(encrypted_refresh_token)
            if not refresh_token:
                raise ValueError("Decryption returned empty value")
        except Exception as err:
            logger.error(
                "Failed to decrypt refresh token for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            # Clear corrupted token
            identity_provider_links_integration.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                user_id, idp_id, db
            )
            return None

        # Resolve endpoints and credentials using helper methods
        token_endpoint = self._resolve_token_endpoint(idp)
        client_id = self._decrypt_client_id(idp)
        client_secret = self._decrypt_client_secret(idp)

        # Create OAuth client for token refresh
        client: OAuth2Client | None = None
        try:
            client = self._create_oauth_client(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=None,  # Not needed for refresh token flow
            )

            # Exchange refresh token for new tokens
            token_response = client.fetch_token(
                token_endpoint,
                grant_type="refresh_token",
                refresh_token=refresh_token,
            )

            logger.debug(
                "Successfully refreshed IdP session for user <user_id>, idp <idp_id>",
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )

            # Store the new tokens (they may include a new refresh token)
            self._store_idp_tokens(user_id, idp_id, token_response, db)

            return token_response

        except httpx2.TimeoutException as err:
            logger.warning(
                "Timeout refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            # Don't clear token - IdP may be temporarily down
            return None

        except httpx2.HTTPStatusError as err:
            # Check if this is a token revocation (400) or auth failure (401)
            if err.response.status_code in (400, 401):
                logger.warning(
                    "IdP refresh token invalid/revoked for user <user_id>, idp <idp_id>: <status_code> - <text>",
                    exc_info=err,
                    extra=core_logger.context(
                        user_id=user_id, idp_id=idp_id, status_code=err.response.status_code, text=err.response.text
                    ),
                )
                # Clear invalid token from database
                identity_provider_links_integration.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                    user_id, idp_id, db
                )
                return None
            else:
                # Other HTTP errors (5xx) - don't clear token
                logger.warning(
                    "HTTP error refreshing IdP session for user <user_id>, idp <idp_id>: <status_code> - <text>",
                    exc_info=err,
                    extra=core_logger.context(
                        user_id=user_id, idp_id=idp_id, status_code=err.response.status_code, text=err.response.text
                    ),
                )
                return None

        except httpx2.RequestError as err:
            logger.warning(
                "Network error refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            # Don't clear token - network issue, not token issue
            return None

        except Exception as err:
            logger.error(
                "Unexpected error refreshing IdP session for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            return None
        finally:
            if client is not None:
                client.close()

    def revoke_idp_token(
        self,
        user_id: int,
        idp_id: int,
        db: Session,
    ) -> bool:
        """Attempt to revoke a refresh token at the IdP (RFC 7009).

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
            success = idp_service.revoke_idp_token(user_id=123, idp_id=1, db=db)
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
                logger.debug(
                    "IdP (ID: <idp_id>) not found or disabled. Skipping token revocation.",
                    extra=core_logger.context(idp_id=idp_id),
                )
                return False

            # Get the encrypted refresh token from database
            encrypted_refresh_token = (
                identity_provider_links_integration.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                    user_id, idp_id, db
                )
            )

            if not encrypted_refresh_token:
                # No token to revoke - consider this success
                logger.debug(
                    "No refresh token to revoke for user <user_id>, idp <idp_id>",
                    extra=core_logger.context(user_id=user_id, idp_id=idp_id),
                )
                return True

            # Decrypt the refresh token
            try:
                refresh_token = core_cryptography.decrypt_token_fernet(encrypted_refresh_token)
                if not refresh_token:
                    logger.warning(
                        "Failed to decrypt refresh token for revocation (user <user_id>, idp <idp_id>)",
                        extra=core_logger.context(user_id=user_id, idp_id=idp_id),
                    )
                    return False
            except Exception as err:
                logger.warning(
                    "Error decrypting refresh token for revocation: <err>",
                    exc_info=err,
                    extra=core_logger.context(err=err),
                )
                return False

            # Try to get revocation endpoint from OIDC discovery
            revocation_endpoint = None
            if idp.issuer_url:
                try:
                    config = self.get_oidc_configuration(idp)
                    if config:
                        revocation_endpoint = config.get("revocation_endpoint")
                except Exception as err:
                    logger.debug(
                        "OIDC discovery failed for revocation endpoint (IdP <name>): <err>",
                        exc_info=err,
                        extra=core_logger.context(name=idp.name, err=err),
                    )

            if not revocation_endpoint:
                # IdP doesn't advertise a revocation endpoint
                logger.debug(
                    "IdP <name> does not support token revocation (no revocation_endpoint). Token will be cleared locally only.",
                    extra=core_logger.context(name=idp.name),
                )
                return False

            # Decrypt client secret and id for authentication
            try:
                client_id = self._decrypt_client_id(idp)
                client_secret = self._decrypt_client_secret(idp)
            except Exception as err:
                logger.warning(
                    "Failed to decrypt client secret or id for revocation: <err>",
                    exc_info=err,
                    extra=core_logger.context(err=err),
                )
                return False

            # Call the revocation endpoint (RFC 7009)
            try:
                with self._http_client() as client:
                    response = client.post(
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
                    logger.info(
                        "Successfully revoked IdP token for user <user_id>, idp <idp_id>",
                        extra=core_logger.context(user_id=user_id, idp_id=idp_id),
                    )
                    return True
                else:
                    logger.warning(
                        "IdP revocation endpoint returned <status_code> for user <user_id>, idp <idp_id>",
                        extra=core_logger.context(status_code=response.status_code, user_id=user_id, idp_id=idp_id),
                    )
                    return False

            except httpx2.TimeoutException as err:
                logger.warning(
                    "Timeout revoking token at IdP <name> for user <user_id>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, user_id=user_id, err=err),
                )
                return False

            except httpx2.RequestError as err:
                logger.warning(
                    "Network error revoking token at IdP <name> for user <user_id>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, user_id=user_id, err=err),
                )
                return False

            except Exception as err:
                logger.warning(
                    "Unexpected error revoking token at IdP <name> for user <user_id>: <err>",
                    exc_info=err,
                    extra=core_logger.context(name=idp.name, user_id=user_id, err=err),
                )
                return False

        except Exception as err:
            # Catch-all for unexpected errors
            logger.error(
                "Error in revoke_idp_token for user <user_id>, idp <idp_id>: <err>",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id, err=err),
            )
            return False

    def _is_token_expired_by_age(self, link: auth_identity_links_contracts.IdentityLinkRead) -> bool:
        """Check if an IdP refresh token has exceeded the maximum age policy.

        According to security best practices, refresh tokens should have a maximum lifetime
        to limit the window of exposure. This method checks if a token is older than the
        configured maximum age.

        Args:
            link (auth_identity_links_contracts.IdentityLinkRead): The user-IdP link containing token metadata.

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

        now = datetime.now(UTC)

        # Determine when the token was first issued or last refreshed
        token_timestamp = link.idp_refresh_token_updated_at or link.linked_at

        if not token_timestamp:
            # No timestamp available - cannot determine age (should not happen)
            logger.warning(
                "Warning: IdP link user_id=<user_id>, idp_id=<idp_id> has no timestamp for age calculation",
                extra=core_logger.context(user_id=link.user_id, idp_id=link.idp_id),
            )
            return False

        # Calculate token age (TIMESTAMPTZ returns aware datetimes)
        token_age = now - token_timestamp

        # Check if token exceeds maximum age
        max_age = timedelta(days=MAX_IDP_TOKEN_AGE_DAYS)
        return token_age > max_age

    def _should_refresh_idp_token(self, link: auth_identity_links_contracts.IdentityLinkRead) -> TokenAction:
        """Determine what action to take for an IdP token based on expiry and age policies.

        This method checks multiple conditions to decide the appropriate action:
        1. Token age - if token exceeds maximum age, it must be cleared
        2. Token existence - whether a refresh token is stored
        3. Token expiry - whether the access token is close to expiry
        4. Rate limiting - whether the token was refreshed very recently

        Args:
            link (auth_identity_links_contracts.IdentityLinkRead): The user-IdP link containing token metadata.

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
            link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
            action = self._should_refresh_idp_token(link)
            if action == TokenAction.REFRESH:
                self.refresh_idp_session(user_id, idp_id, db)
            elif action == TokenAction.CLEAR:
                identity_provider_links_integration.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(user_id, idp_id, db)
        """
        # Check if refresh token exists
        if not link or not link.idp_refresh_token:
            return TokenAction.SKIP

        # Check if token has exceeded maximum age (security policy)
        if self._is_token_expired_by_age(link):
            logger.info(
                "IdP refresh token for user_id=<user_id>, idp_id=<idp_id> has exceeded maximum age (<MAX_IDP_TOKEN_AGE_DAYS> days). Will be cleared.",
                extra=core_logger.context(
                    user_id=link.user_id, idp_id=link.idp_id, MAX_IDP_TOKEN_AGE_DAYS=MAX_IDP_TOKEN_AGE_DAYS
                ),
            )
            return TokenAction.CLEAR

        # Check if we know when the access token expires
        if not link.idp_access_token_expires_at:
            # No expiry info - assume token is still valid
            return TokenAction.SKIP

        now = datetime.now(UTC)

        # Check if token was refreshed very recently (rate limiting)
        if link.idp_refresh_token_updated_at:
            time_since_refresh = now - link.idp_refresh_token_updated_at
            if time_since_refresh < timedelta(minutes=TOKEN_REFRESH_RATE_LIMIT_MINUTES):
                # Refreshed less than defined - don't refresh again
                return TokenAction.SKIP

        # Check if access token is close to expiry
        time_until_expiry = link.idp_access_token_expires_at - now
        if time_until_expiry < timedelta(minutes=TOKEN_EXPIRY_THRESHOLD_MINUTES):
            # Token expires soon - should refresh
            return TokenAction.REFRESH

        # Token is still valid and not close to expiry
        return TokenAction.SKIP
