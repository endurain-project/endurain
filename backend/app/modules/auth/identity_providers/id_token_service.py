"""Verification of OIDC ID tokens against the identity provider's published signing keys."""

import base64
import json
from collections.abc import Callable
from typing import Any

from joserfc import jwt
from joserfc.errors import (
    BadSignatureError,
    ExpiredTokenError,
    InvalidClaimError,
    InvalidPayloadError,
    MissingClaimError,
)
from joserfc.jwk import ECKey, OctKey, RSAKey

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

#: Clock skew tolerated between this server and the provider on ``exp`` and ``iat``.
ID_TOKEN_CLOCK_LEEWAY_SECONDS = 60

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


def verify_id_token(
    fetch_jwks: Callable[[str], dict[str, Any]],
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
    6. Validates standard claims (iss, aud, exp, iat), allowing a small clock skew, and the authorized party
    7. Validates nonce if provided (required for implicit/hybrid flows)

    This replaces the insecure manual JWT decode that was previously used.

    Args:
        fetch_jwks: Returns the provider's JWKS for a JWKS URI; called only once the token header is accepted
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
        jwks = fetch_jwks(jwks_uri)

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
            leeway=ID_TOKEN_CLOCK_LEEWAY_SECONDS,
            iss={"essential": True, "value": expected_issuer},
            aud={"essential": True, "value": expected_audience},
            exp={"essential": True},
            iat={"essential": True},
        )

        # Validate all claims
        claims_request.validate(claims)
        _require_authorized_party(claims, expected_audience)

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
                # The nonce values are not logged: the expected one is the secret binding this login.
                logger.warning("ID token nonce does not match the one issued for this login")
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
        logger.debug("Unexpected error verifying ID token: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.ProcessingError("Failed to verify ID token") from err


def _require_authorized_party(claims: dict[str, Any], client_id: str) -> None:
    """Require the token to have been issued to this client when it names an authorized party (OIDC Core 3.1.3.7).

    A token with several audiences must say which of them it was issued to, and an ``azp`` that names another
    client means the token was issued to that client and only lists this one as an audience.

    Args:
        claims: The ID token's claims, already validated for ``aud``.
        client_id: This server's client id at the provider.

    Raises:
        UnauthenticatedError: If ``azp`` names another client, or is missing from a token with several audiences.
    """
    azp = claims.get("azp")
    audience = claims.get("aud")
    if azp is None and isinstance(audience, list) and len(audience) > 1:
        logger.warning("ID token has several audiences and no authorized party")
        raise core_exceptions.UnauthenticatedError("ID token names no authorized party")
    if azp is not None and azp != client_id:
        logger.warning("ID token was issued to another client")
        raise core_exceptions.UnauthenticatedError("ID token was issued to another client")
