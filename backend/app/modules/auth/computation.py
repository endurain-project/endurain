"""Pure helpers the auth packages share: token hashing and the cookie ``Secure`` rule.

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

import base64
import hashlib
import hmac
import re
import secrets

import core.environment as core_environment
import core.exceptions as core_exceptions
import core.hashing as core_hashing


def generate_token_and_hash() -> tuple[str, str]:
    """Generate a URL-safe random token and its SHA-256 hash.

    Returns:
        ``(token, token_hash)``. Store the hash in the database and hand the raw
        token to the user through the outbound channel (email link).
    """
    token = secrets.token_urlsafe(32)
    return token, sha256_hex(token)


def sha256_hex(value: str) -> str:
    """Return the SHA-256 hex digest of ``value``.

    Args:
        value: The plaintext token to hash.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 chars).
    """
    return core_hashing.sha256_hex(value)


def hmac_sha256(value: str, secret_key: str) -> str:
    """Return the keyed HMAC-SHA256 hex digest of ``value``.

    Args:
        value: The plaintext token to hash.
        secret_key: Secret key used to create the keyed digest.

    Returns:
        Lowercase hex-encoded HMAC-SHA256 digest (64 chars).

    Raises:
        ValueError: If ``secret_key`` is empty.
    """
    if not secret_key:
        raise ValueError("secret_key must not be empty")
    return hmac.new(
        secret_key.encode(),
        value.encode(),
        hashlib.sha256,
    ).hexdigest()


def validate_pkce_challenge(code_challenge: str, code_challenge_method: str) -> None:
    """Validate a PKCE challenge according to RFC 7636."""
    if code_challenge_method != "S256":
        raise core_exceptions.InvalidInputError("Only S256 PKCE method is supported")
    if not 43 <= len(code_challenge) <= 128:
        raise core_exceptions.InvalidInputError("code_challenge must be 43-128 characters")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", code_challenge):
        raise core_exceptions.InvalidInputError("code_challenge must be valid base64url")


def validate_pkce_verifier(code_verifier: str, code_challenge: str, code_challenge_method: str) -> None:
    """Validate PKCE code_verifier and verify it matches the code_challenge.

    This function implements RFC 7636 PKCE verification by computing the
    SHA256 hash of the verifier and comparing it to the stored challenge.
    This proves the client possesses the secret used during login initiation.

    Args:
        code_verifier (str): Base64url-encoded verifier from mobile client.
        code_challenge (str): Base64url-encoded SHA256 hash stored in DB.
        code_challenge_method (str): PKCE method (must be "S256").

    Raises:
        InvalidInputError: If the verifier format is invalid, the method is not S256, or the verifier does not
            match the challenge.
    """
    # Validate verifier format
    if not (43 <= len(code_verifier) <= 128):
        raise core_exceptions.InvalidInputError("code_verifier must be 43-128 characters")

    if not re.match(r"^[A-Za-z0-9_-]+$", code_verifier):
        raise core_exceptions.InvalidInputError("code_verifier must be valid base64url")

    # Verify method is S256
    if code_challenge_method != "S256":
        raise core_exceptions.InvalidInputError("Only S256 PKCE method is supported")

    # Compute SHA256 hash of verifier
    verifier_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed_challenge = base64.urlsafe_b64encode(verifier_hash).decode("ascii").rstrip("=")

    # Constant-time comparison to prevent timing attacks
    if not _secure_compare(computed_challenge, code_challenge):
        raise core_exceptions.InvalidInputError("Invalid code_verifier")


def _secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks.

    Uses ``hmac.compare_digest`` to avoid both character-by-
    character and length timing leaks.

    Args:
        a: First string.
        b: Second string.

    Returns:
        True if strings are equal, False otherwise.
    """
    return hmac.compare_digest(a.encode(), b.encode())


def secure_cookie(environment: str) -> bool:
    """Return whether the configured environment requires Secure cookies.

    Args:
        environment: The deployment environment name.

    Returns:
        True when auth cookies must only travel over HTTPS.
    """
    return core_environment.is_deployed_environment(environment)
