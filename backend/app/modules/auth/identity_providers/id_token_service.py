"""Verification of the JWTs an identity provider signs, ID tokens and logout tokens, against its published keys."""

import base64
import hashlib
import hmac
import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, NoReturn, Protocol

from joserfc import jwt
from joserfc.errors import (
    BadSignatureError,
    DecodeError,
    ExpiredTokenError,
    InvalidClaimError,
    InvalidKeyTypeError,
    InvalidPayloadError,
    MissingClaimError,
)
from joserfc.jwk import ECKey, RSAKey

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
# ``EdDSA`` is left out too: joserfc refuses it unless a caller opts in, and only
# RSA and EC keys are imported from the JWKS.
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
    }
)


#: The media types a logout token's ``typ`` header may name: its own (OIDC Back-Channel Logout 1.0, section 2.4) and
#: the generic JWT one (RFC 7519, section 5.1).
_LOGOUT_TOKEN_MEDIA_TYPES = frozenset({"application/logout+jwt", "application/jwt"})

#: The member of a logout token's ``events`` claim that declares it a back-channel logout.
BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"

#: Longest ``sub`` a logout token may name: the length of a stored provider subject.
MAX_SUBJECT_LENGTH = 500

#: Longest ``sid`` an ID token or logout token may name: the length of a stored provider session id.
MAX_SESSION_ID_LENGTH = 255

#: The JWK key type that signs with each family of ``alg`` values.
_KEY_TYPE_BY_ALG_PREFIX = {"RS": "RSA", "PS": "RSA", "ES": "EC"}


def _can_verify(key_data: dict[str, Any], alg: str) -> bool:
    """Return whether a JWK may verify a signature made with ``alg``."""
    if key_data.get("use", "sig") != "sig":
        return False
    if key_data.get("kty") != _KEY_TYPE_BY_ALG_PREFIX.get(alg[:2]):
        return False
    return key_data.get("alg", alg) == alg


def _find_key(jwks: dict[str, Any], kid: str | None, alg: str) -> dict[str, Any] | None:
    """Return the key that verifies a token from a JWKS, or None.

    A token that names a ``kid`` takes the key with that ``kid``, provided the key is usable for ``alg`` (signature
    use, matching ``kty`` and, when the key declares one, ``alg``). A token without one is accepted only when the
    set holds exactly one key usable for ``alg``, because OIDC requires a ``kid`` only when the set holds several
    keys.

    Args:
        jwks: The provider's JWKS document.
        kid: The ``kid`` of the token header, if it has one.
        alg: The ``alg`` of the token header.

    Returns:
        The key, or None when no key, or more than one key, could have signed the token.
    """
    keys = jwks.get("keys", [])
    if kid is not None:
        return next((key_data for key_data in keys if key_data.get("kid") == kid and _can_verify(key_data, alg)), None)
    candidates = [key_data for key_data in keys if _can_verify(key_data, alg)]
    return candidates[0] if len(candidates) == 1 else None


class FetchJwks(Protocol):
    """Return a provider's JWKS document."""

    def __call__(self, jwks_uri: str, *, refresh: bool = False) -> dict[str, Any]:
        """Return the JWKS published at a URI.

        Args:
            jwks_uri: The provider's JWKS URI.
            refresh: Whether to fetch the document again instead of reading the cached one.

        Returns:
            The JWKS document.
        """
        ...


def verify_id_token(
    fetch_jwks: FetchJwks,
    id_token: str,
    jwks_uri: str,
    expected_issuer: str,
    expected_audience: str,
    expected_nonce: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Verify an ID token's signature and claims against the identity provider's signing keys (OIDC Core 3.1.3.7).

    The signature is checked by :func:`_decode_signed`. The claims must then name the expected issuer and audience
    (with the authorized party rule), a subject, an expiry and an issue time, each time allowing
    ``ID_TOKEN_CLOCK_LEEWAY_SECONDS`` of clock skew, and the nonce of the authorization request when one is expected.
    When the token carries an ``at_hash`` and the access token issued with it is given, the hash must match it
    (OIDC Core 3.1.3.6).

    Args:
        fetch_jwks: Returns the provider's JWKS for a JWKS URI and, called with ``refresh=True``, a freshly fetched
            one; called only once the token header is accepted.
        id_token: The ID token from the token response.
        jwks_uri: The provider's JWKS URI.
        expected_issuer: The ``iss`` the provider's discovery document names.
        expected_audience: This server's client id at the provider.
        expected_nonce: The nonce stored with the authorization request, when one must match.
        access_token: The access token the provider issued with the ID token, when there is one.

    Returns:
        The verified claims.

    Raises:
        UnauthenticatedError: If the token is malformed, uses a refused algorithm or an unknown key, its signature
            does not verify, or a claim is missing, expired or does not match.
        ProcessingError: If the verification fails unexpectedly.
    """
    with _verification_errors("ID token"):
        decoded = _decode_signed(fetch_jwks, id_token, jwks_uri, "ID token")
        claims = decoded.claims
        jwt.JWTClaimsRegistry(
            leeway=ID_TOKEN_CLOCK_LEEWAY_SECONDS,
            iss={"essential": True, "value": expected_issuer},
            aud={"essential": True, "value": expected_audience},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
        ).validate(claims)
        _require_authorized_party(claims, expected_audience)

        logger.debug(
            "Successfully verified ID token signature for sub=<value_1>",
            extra=core_logger.context(value_1=claims.get("sub")),
        )

        # The nonce binds the token to the authorization request that started this sign-in.
        if expected_nonce:
            token_nonce = claims.get("nonce")
            if not token_nonce:
                logger.warning("ID token missing nonce claim but nonce was expected")
                raise core_exceptions.UnauthenticatedError("ID token missing nonce")

            if token_nonce != expected_nonce:
                # The nonce values are not logged: the expected one is the secret binding this login.
                logger.warning("ID token nonce does not match the one issued for this login")
                raise core_exceptions.UnauthenticatedError("ID token nonce mismatch")

        if access_token is not None and "at_hash" in claims:
            _require_access_token_hash(claims["at_hash"], access_token, decoded.header["alg"])

        return claims


def verify_logout_token(
    fetch_jwks: FetchJwks,
    logout_token: str,
    jwks_uri: str,
    expected_issuer: str,
    expected_audience: str,
) -> dict[str, Any]:
    """Verify a back-channel logout token's signature and claims (OIDC Back-Channel Logout 1.0, section 2.6).

    The signature, algorithm and key are checked exactly as for an ID token (:func:`_decode_signed`). A ``typ``
    header, when present, must be ``logout+jwt`` or the generic ``JWT`` that most JWT libraries write by default:
    the specification recommends explicit typing to issuers but warns that requiring it breaks most deployments
    (section 4.1), so only a token typed as something else is refused. ``iss``, ``aud`` (with the authorized party
    rule), ``iat`` and ``exp`` are validated as for an ID token; ``jti`` is required; ``events`` must be an object whose
    back-channel logout member is an object; the token must name a ``sub``, a ``sid`` or both, each a non-empty
    bounded string; and it must not carry a ``nonce``, so an ID token cannot pass for a logout token.

    Args:
        fetch_jwks: Returns the provider's JWKS for a JWKS URI and, called with ``refresh=True``, a freshly fetched
            one; called only once the token header is accepted.
        logout_token: The ``logout_token`` the provider posted.
        jwks_uri: The provider's JWKS URI.
        expected_issuer: The ``iss`` the provider's discovery document names.
        expected_audience: This server's client id at the provider.

    Returns:
        The verified claims.

    Raises:
        UnauthenticatedError: If the token is malformed or not a logout token, uses a refused algorithm or an
            unknown key, its signature does not verify, or a claim is missing, expired or does not match.
        ProcessingError: If the verification fails unexpectedly.
    """
    with _verification_errors("Logout token"):
        decoded = _decode_signed(fetch_jwks, logout_token, jwks_uri, "Logout token")
        typ = decoded.header.get("typ")
        if typ is not None and not _is_logout_token_type(typ):
            logger.warning("Logout token has type <typ>", extra=core_logger.context(typ=typ))
            raise core_exceptions.UnauthenticatedError("Logout token has the wrong type")
        claims = decoded.claims
        jwt.JWTClaimsRegistry(
            leeway=ID_TOKEN_CLOCK_LEEWAY_SECONDS,
            iss={"essential": True, "value": expected_issuer},
            aud={"essential": True, "value": expected_audience},
            exp={"essential": True},
            iat={"essential": True},
            jti={"essential": True},
            events={"essential": True},
        ).validate(claims)
        _require_authorized_party(claims, expected_audience)
        _require_logout_claims(claims)
        return claims


def _is_logout_token_type(typ: object) -> bool:
    """Tell whether a ``typ`` header allows the token to be a logout token.

    A ``typ`` is a media type compared without regard to case, with ``application/`` implied when it names no
    top-level type (RFC 7515, section 4.1.9). ``logout+jwt`` types the token explicitly; ``JWT`` types it as a JWT
    of no particular kind (RFC 7519, section 5.1).

    Args:
        typ: The ``typ`` header value.

    Returns:
        True when it names ``application/logout+jwt`` or ``application/jwt``.
    """
    if not isinstance(typ, str):
        return False
    media_type = typ.lower()
    if "/" not in media_type:
        media_type = f"application/{media_type}"
    return media_type in _LOGOUT_TOKEN_MEDIA_TYPES


def _require_logout_claims(claims: dict[str, Any]) -> None:
    """Require the claims that make a JWT a logout token and refuse the one that makes it an ID token.

    Args:
        claims: The token's claims, already validated for the registered claims.

    Raises:
        UnauthenticatedError: If ``events`` does not declare a back-channel logout, neither ``sub`` nor ``sid``
            is present, either is not a non-empty bounded string, or a ``nonce`` is present.
    """
    events = claims["events"]
    if not isinstance(events, dict) or not isinstance(events.get(BACKCHANNEL_LOGOUT_EVENT), dict):
        logger.warning("Logout token does not declare a back-channel logout event")
        raise core_exceptions.UnauthenticatedError("Logout token events claim does not declare a logout")
    if "nonce" in claims:
        logger.warning("Logout token carries a nonce")
        raise core_exceptions.UnauthenticatedError("Logout token must not carry a nonce")
    if "sub" not in claims and "sid" not in claims:
        logger.warning("Logout token names neither a subject nor a session")
        raise core_exceptions.UnauthenticatedError("Logout token names neither sub nor sid")
    for name, max_length in (("sub", MAX_SUBJECT_LENGTH), ("sid", MAX_SESSION_ID_LENGTH)):
        value = claims.get(name)
        if name in claims and not (isinstance(value, str) and 0 < len(value) <= max_length):
            logger.warning("Logout token <name> claim is not a usable string", extra=core_logger.context(name=name))
            raise core_exceptions.UnauthenticatedError(f"Logout token {name} claim is invalid")


def _read_header(token: str, kind: str) -> dict[str, Any]:
    """Read the protected header of a compact JWS without verifying it.

    Args:
        token: The token.
        kind: What the token is, for messages ("ID token").

    Returns:
        The header.

    Raises:
        UnauthenticatedError: If the token is not three dot-separated parts or its header is not a JSON object.
    """
    parts = token.split(".")
    if len(parts) != 3:
        logger.warning(
            "Invalid JWT format: expected 3 parts, got <value_1>", extra=core_logger.context(value_1=len(parts))
        )
        raise core_exceptions.UnauthenticatedError(f"Invalid {kind} format")
    header_b64 = parts[0] + "=" * (-len(parts[0]) % 4)
    try:
        header = json.loads(base64.urlsafe_b64decode(header_b64))
    except ValueError as err:
        logger.warning("JWT header is not base64url-encoded JSON", exc_info=err)
        raise core_exceptions.UnauthenticatedError(f"Invalid {kind} format") from err
    if not isinstance(header, dict):
        logger.warning("JWT header is not a JSON object")
        raise core_exceptions.UnauthenticatedError(f"Invalid {kind} format")
    return header


def _import_key(jwk: dict[str, Any]) -> RSAKey | ECKey:
    """Import a JWKS entry as a key, accepting only RSA and EC.

    Args:
        jwk: The JWKS entry.

    Returns:
        The key.

    Raises:
        UnauthenticatedError: If the entry is of another key type.
    """
    key_type = jwk.get("kty")
    if key_type == "RSA":
        return RSAKey.import_key(jwk)
    if key_type == "EC":
        return ECKey.import_key(jwk)
    logger.warning("Unsupported key type in JWKS: <key_type>", extra=core_logger.context(key_type=key_type))
    raise core_exceptions.UnauthenticatedError(f"Unsupported key type: {key_type}")


def _refuse_unknown_key(kid: Any, alg: Any, kind: str) -> NoReturn:
    """Refuse a token whose JWKS names no single key for it.

    Args:
        kid: The token header's ``kid``, if any.
        alg: The token header's ``alg``.
        kind: What the token is, for messages ("ID token").

    Raises:
        UnauthenticatedError: Always.
    """
    logger.warning(
        "No single matching key found in JWKS for kid=<kid>, alg=<alg>", extra=core_logger.context(kid=kid, alg=alg)
    )
    raise core_exceptions.UnauthenticatedError(f"{kind} signed with unknown key")


def _decode_signed(fetch_jwks: FetchJwks, token: str, jwks_uri: str, kind: str) -> jwt.Token:
    """Verify a provider-signed JWT's signature against the provider's JWKS and return its header and claims.

    1. The header must name an ``alg`` from ``ID_TOKEN_ALLOWED_ALGORITHMS``; the JWKS is fetched only then.
    2. The key is the one with the header's ``kid``, or, for a token without one, the only key usable for its
       ``alg``; when the cached set has none, it is fetched afresh.
    3. Only an RSA or EC key is imported, and joserfc verifies the signature with the allow-list pinned, so a
       forged ``alg`` cannot bypass verification.
    4. When the signature does not verify with a key from the cached set, the provider may have rotated that key
       under the same ``kid``, so the set is fetched afresh and the signature verified once more with the key it
       gives. The set is fetched afresh at most once per verification.

    No claim is checked here.

    Args:
        fetch_jwks: Returns the provider's JWKS, cached or, with ``refresh=True``, freshly fetched.
        token: The compact JWS.
        jwks_uri: The provider's JWKS URI.
        kind: What the token is, for messages ("ID token").

    Returns:
        The verified token.

    Raises:
        UnauthenticatedError: If the token is malformed, uses a refused algorithm or names no usable key.
        BadSignatureError: If the signature does not verify with the key of the freshly fetched set.
    """
    header = _read_header(token, kind)
    kid = header.get("kid")
    alg = header.get("alg")

    if not alg:
        logger.warning("JWT header missing 'alg' claim")
        raise core_exceptions.UnauthenticatedError(f"{kind} missing algorithm")

    # Reject disallowed algorithms before importing the key. This blocks ``alg=none`` and symmetric ``HS*``
    # algorithms, which would otherwise enable signature-bypass and RS256→HS256 key-confusion attacks against the
    # public JWKS keys.
    if alg not in ID_TOKEN_ALLOWED_ALGORITHMS:
        logger.warning("JWT uses disallowed algorithm: <alg>", extra=core_logger.context(alg=alg))
        raise core_exceptions.UnauthenticatedError(f"{kind} uses an unsupported signature algorithm")

    logger.debug("JWT header: kid=<kid>, alg=<alg>", extra=core_logger.context(kid=kid, alg=alg))

    # A key the cached set lacks (or, without a kid, a set that does not single one out) may have changed since, so
    # the set is fetched afresh once before the token is refused.
    refreshed = False
    matching_key = _find_key(fetch_jwks(jwks_uri), kid, alg)
    if matching_key is None:
        matching_key = _find_key(fetch_jwks(jwks_uri, refresh=True), kid, alg)
        refreshed = True

    if not matching_key:
        _refuse_unknown_key(kid, alg, kind)

    try:
        return jwt.decode(token, _import_key(matching_key), algorithms=list(ID_TOKEN_ALLOWED_ALGORITHMS))
    except BadSignatureError:
        if refreshed:
            raise

    # The provider may have rotated the key's material under the cached kid; verify once more with the fresh one.
    matching_key = _find_key(fetch_jwks(jwks_uri, refresh=True), kid, alg)
    if not matching_key:
        _refuse_unknown_key(kid, alg, kind)
    return jwt.decode(token, _import_key(matching_key), algorithms=list(ID_TOKEN_ALLOWED_ALGORITHMS))


@contextmanager
def _verification_errors(kind: str) -> Generator[None]:
    """Turn the errors of a JWT verification into domain errors.

    A token the signature or claim checks refuse is an ``UnauthenticatedError``; a domain error raised inside
    (including one from fetching the JWKS) passes through; anything else is a ``ProcessingError``.

    Args:
        kind: What the token is, for messages ("ID token").

    Yields:
        Nothing; the verification runs in the block.

    Raises:
        UnauthenticatedError: If the token is refused.
        ProcessingError: If the verification fails unexpectedly.
    """
    try:
        yield
    except BadSignatureError as err:
        logger.warning("JWT signature verification failed: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"{kind} signature is invalid") from err
    except InvalidKeyTypeError as err:
        # The kid names a key of another type than the token's algorithm needs, so it cannot verify it.
        logger.warning("JWT key does not fit its algorithm: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"{kind} signed with an unusable key") from err
    except DecodeError as err:
        logger.warning("JWT segments are malformed: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"Invalid {kind} format") from err
    except ExpiredTokenError as err:
        logger.warning("JWT has expired: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"{kind} has expired") from err
    except InvalidClaimError as err:
        logger.warning("JWT claim validation failed: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"{kind} claim validation failed: {err}") from err
    except MissingClaimError as err:
        logger.warning("JWT missing required claim: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"{kind} missing required claim: {err}") from err
    except InvalidPayloadError as err:
        logger.warning("JWT payload is invalid: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.UnauthenticatedError(f"{kind} payload is invalid") from err
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        logger.debug("Unexpected error verifying a JWT: <err>", exc_info=err, extra=core_logger.context(err=err))
        raise core_exceptions.ProcessingError(f"Failed to verify {kind}") from err


def _require_access_token_hash(at_hash: object, access_token: str, alg: str) -> None:
    """Require an ID token's ``at_hash`` to be the hash of the access token issued with it (OIDC Core 3.1.3.6).

    The hash is the base64url encoding of the left half of the digest of the access token, made with the hash
    the token's signature algorithm uses (SHA-256, SHA-384 or SHA-512 by the number ending the algorithm name).

    Args:
        at_hash: The ID token's ``at_hash`` claim.
        access_token: The access token the provider issued with the ID token.
        alg: The ``alg`` of the ID token header, already on the allow-list.

    Raises:
        UnauthenticatedError: If ``at_hash`` is not the hash of the access token.
    """
    digest = hashlib.new(f"sha{alg[-3:]}", access_token.encode("ascii", "replace")).digest()
    expected = base64.urlsafe_b64encode(digest[: len(digest) // 2]).decode().rstrip("=")
    if not isinstance(at_hash, str) or not hmac.compare_digest(at_hash.encode(), expected.encode()):
        logger.warning("ID token at_hash does not match the access token")
        raise core_exceptions.UnauthenticatedError("ID token at_hash does not match the access token")


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
