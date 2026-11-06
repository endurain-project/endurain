"""The JWT signing algorithm, secrets and signature check shared by everything that reads an access token.

The authentication module issues and validates access tokens; the rate limiter reads one before
authentication runs to name a per-user bucket. Both take the algorithm allow-list, the keys and the
signature check from here, so they cannot drift apart. Each keeps its own claims rules.

``SECRET_KEY`` may list several secrets, so there are several keys: the first signs and every one verifies.
Each token names the key that signed it in its ``kid`` header, and the key is picked by that id.
"""

import functools
import hashlib
from collections.abc import Sequence
from typing import Final

from joserfc import jwt
from joserfc.jwk import KeySet, OctKey
from joserfc.jwt import Token

import core.config as core_config
import core.key_derivation as core_key_derivation

ALLOWED_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256"})
ALGORITHM: Final[str] = core_config.read_secret("ALGORITHM", "HS256") or "HS256"
if ALGORITHM not in ALLOWED_ALGORITHMS:
    raise ValueError(f"ALGORITHM={ALGORITHM!r} is not in the allow-list {sorted(ALLOWED_ALGORITHMS)}.")

#: The JOSE ``typ`` of an access token (RFC 9068 section 2.1).
ACCESS_JWT_TYP: Final[str] = "at+jwt"
#: The JOSE ``typ`` of a refresh token, so a refresh token cannot pass as an access token and the reverse.
REFRESH_JWT_TYP: Final[str] = "rt+jwt"

#: The derived keys in ``SECRET_KEY`` order; the first signs, every one verifies. Empty when no secret is set.
SIGNING_KEYS: Final[tuple[str, ...]] = core_key_derivation.derive_keys(core_key_derivation.JWT)
#: The key that signs, or ``None`` when no secret is set.
SIGNING_KEY: Final[str | None] = SIGNING_KEYS[0] if SIGNING_KEYS else None


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
    """Return the keys that verify tokens, or ``None`` when no secret is set."""
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
