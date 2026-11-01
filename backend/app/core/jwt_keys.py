"""The JWT signing algorithm, secret and signature check shared by everything that reads an access token.

The authentication module issues and validates access tokens; the rate limiter reads one before
authentication runs to name a per-user bucket. Both take the algorithm allow-list, the secret and the
signature check from here, so they cannot drift apart. Each keeps its own claims rules.
"""

import functools
from typing import Final

from joserfc import jwt
from joserfc.jwk import OctKey
from joserfc.jwt import Token

import core.config as core_config

ALLOWED_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256"})
ALGORITHM: Final[str] = core_config.read_secret("ALGORITHM", "HS256") or "HS256"
if ALGORITHM not in ALLOWED_ALGORITHMS:
    raise ValueError(f"ALGORITHM={ALGORITHM!r} is not in the allow-list {sorted(ALLOWED_ALGORITHMS)}.")
SECRET_KEY: Final[str | None] = core_config.read_secret("SECRET_KEY")


@functools.cache
def verification_key() -> OctKey | None:
    """Return the key that signs and verifies tokens, or ``None`` when no secret is set."""
    return OctKey.import_key(SECRET_KEY) if SECRET_KEY else None


def decode(token: str, key: OctKey, algorithm: str = ALGORITHM) -> Token:
    """Check a token's signature and return it decoded.

    The algorithm allow-list is mandatory: without it ``joserfc`` would accept any algorithm the token
    header advertises (``none`` or an asymmetric one), letting an attacker bypass the HMAC check.

    Args:
        token: The encoded JWT.
        key: The key to verify the signature with.
        algorithm: The one algorithm the token must use.

    Returns:
        The decoded token; its ``claims`` are not validated.

    Raises:
        JoseError: If the token is malformed or its signature or algorithm is wrong.
    """
    return jwt.decode(token, key, algorithms=[algorithm])
