"""The JWT signing algorithm, keys, clock leeway and signature check shared by everything that reads Endurain's tokens.

The authentication module issues and validates access and refresh tokens; the rate limiter reads an access token
before authentication runs to name a per-user bucket. Both take the algorithm allow-list, the keys, the leeway and
the signature check from here, so they cannot drift apart. Each keeps its own claims rules.

Access and refresh tokens are signed with keys derived for different purposes, so one kind never verifies as the
other. ``SECRET_KEY`` may list several secrets, so each kind has several keys: the first signs and every one
verifies. Each token names the key that signed it in its ``kid`` header, and the key is picked by that id.
"""

import functools
import hashlib
from collections.abc import Sequence
from typing import Final

from joserfc import jwt
from joserfc.jwk import KeySet, OctKey
from joserfc.jwt import Token

import core.key_derivation as core_key_derivation

ALLOWED_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256"})
ALGORITHM: Final[str] = "HS256"

#: The JOSE ``typ`` of an access token (RFC 9068 section 2.1).
ACCESS_JWT_TYP: Final[str] = "at+jwt"
#: The JOSE ``typ`` of a refresh token, so a refresh token cannot pass as an access token and the reverse.
REFRESH_JWT_TYP: Final[str] = "rt+jwt"

#: Seconds of clock difference forgiven when ``iat``, ``nbf`` and ``exp`` are checked (RFC 7519 sections 4.1.4 and
#: 4.1.5 allow "some small leeway"). Replicas sign and verify with their own clocks: a token minted by a replica whose
#: clock runs ahead carries an ``iat`` and ``nbf`` that another replica sees in the future, and without a leeway it is
#: refused the moment it is issued. A minute covers the drift of hosts kept in time by NTP with a wide margin, as the
#: leeway for identity-provider ID tokens does. It lengthens no session: an access token is honoured only while its
#: session is alive and a refresh token only against its session row, whose expiry is checked without a leeway.
CLOCK_LEEWAY_SECONDS: Final[int] = 60

#: The access-token keys in ``SECRET_KEY`` order; the first signs, every one verifies. Empty when no secret is set.
SIGNING_KEYS: Final[tuple[str, ...]] = core_key_derivation.derive_keys(core_key_derivation.JWT)
#: The refresh-token keys in ``SECRET_KEY`` order; the first signs, every one verifies. Empty when no secret is set.
REFRESH_SIGNING_KEYS: Final[tuple[str, ...]] = core_key_derivation.derive_keys(core_key_derivation.REFRESH_JWT)


def key_id(key: str) -> str:
    """Return the ``kid`` that names a key.

    The id is a truncated digest of the key, so it identifies the key without disclosing it.

    Args:
        key: The derived signing key.

    Returns:
        A 16-character hex id.
    """
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def import_key(key: str) -> OctKey:
    """Import a derived key under its ``kid``.

    Args:
        key: The derived signing key.

    Returns:
        The key, carrying its ``kid``.
    """
    return OctKey.import_key(key, {"kid": key_id(key)})


def key_set(keys: Sequence[str]) -> KeySet:
    """Build the set a token's signature is checked against.

    Args:
        keys: The derived keys.

    Returns:
        The keys, each under its ``kid``, so a token is checked with the key it names.
    """
    return KeySet([import_key(key) for key in keys])


@functools.cache
def verification_keys() -> KeySet | None:
    """Return the keys that verify access tokens, or ``None`` when no secret is set."""
    return key_set(SIGNING_KEYS) if SIGNING_KEYS else None


def decode(token: str, keys: OctKey | KeySet, algorithm: str = ALGORITHM) -> Token:
    """Check a token's signature and return it decoded.

    The algorithm allow-list is mandatory: without it ``joserfc`` would accept any algorithm the token
    header advertises (``none`` or an asymmetric one), letting an attacker bypass the HMAC check.

    Args:
        token: The encoded JWT.
        keys: The key, or the keys, to verify the signature with; a key set picks the one the token's ``kid`` names.
        algorithm: The one algorithm the token must use.

    Returns:
        The decoded token; its ``claims`` are not validated.

    Raises:
        JoseError: If the token is malformed or its signature, algorithm or key id is wrong.
    """
    return jwt.decode(token, keys, algorithms=[algorithm])
