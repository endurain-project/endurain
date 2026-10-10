"""Shared hashing helpers for opaque auth tokens.

Centralizes the two token-hashing strategies used across the auth token
modules so the choice is made in one place and cannot drift:

- :func:`sha256_hex` — plain SHA-256 hex digest. Used for high-entropy,
  single-purpose opaque tokens (API keys, password-reset, sign-up, and IdP
  link tokens). These are 256-bit ``secrets.token_urlsafe(32)`` values, so a
  slow KDF (Argon2/bcrypt) is unnecessary; SHA-256 is the standard choice for
  hashing tokens of this entropy level.
- :func:`hmac_sha256` — keyed HMAC-SHA256 using the server ``JWT_SECRET_KEY``.
  Used for refresh-token reuse detection and CSRF tokens, where a keyed MAC
  adds defense-in-depth: even with database read access an attacker cannot
  verify stolen tokens without the server secret.

Both return a lowercase hex digest and are deterministic, enabling indexed
equality lookups.
"""

import hashlib
import hmac

import core.hashing as core_hashing
import modules.auth.constants as auth_constants


def sha256_hex(value: str) -> str:
    """Return the SHA-256 hex digest of ``value``.

    Args:
        value: The plaintext token to hash.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 chars).
    """
    return core_hashing.sha256_hex(value)


def hmac_sha256(value: str) -> str:
    """Return the keyed HMAC-SHA256 hex digest of ``value``.

    Uses the server ``JWT_SECRET_KEY`` as the HMAC key so the digest is
    unforgeable without the server secret, while remaining microseconds-fast
    (unlike Argon2, which is designed for password storage).

    Args:
        value: The plaintext token to hash.

    Returns:
        Lowercase hex-encoded HMAC-SHA256 digest (64 chars).

    Raises:
        ValueError: If ``JWT_SECRET_KEY`` is not configured.
    """
    secret_key = auth_constants.JWT_SECRET_KEY
    if not secret_key:
        raise ValueError("JWT_SECRET_KEY is not configured")
    return hmac.new(
        secret_key.encode(),
        value.encode(),
        hashlib.sha256,
    ).hexdigest()
