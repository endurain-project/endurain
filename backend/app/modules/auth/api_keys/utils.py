"""User API key utility functions."""

import json
import secrets
from collections.abc import Sequence

import modules.auth.computation as token_hashing


def generate_api_key() -> str:
    """Generate a new raw API key.

    Keys have the format ``endurain_<token>`` where
    ``<token>`` is 32 cryptographically random bytes
    encoded as base64url (43 characters). Total entropy
    is 256 bits.

    Returns:
        A new raw API key string.
    """
    return f"endurain_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """Compute the SHA-256 hex digest of a raw API key.

    High-entropy secrets do not require a slow KDF
    (Argon2/bcrypt). SHA-256 is the industry standard
    for hashing tokens of this entropy level.

    Args:
        raw_key: The plain-text API key to hash.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 chars).
    """
    return token_hashing.sha256_hex(raw_key)


def scopes_to_json(scopes: Sequence[str]) -> str:
    """Serialize scope strings to a JSON array.

    Args:
        scopes: The scopes, plain strings or ``ApiKeyScope`` members, which are stored as their values.

    Returns:
        JSON-encoded string representation.
    """
    return json.dumps(list(scopes))


def json_to_scopes(scopes_json: str) -> list[str]:
    """Deserialize a JSON string to a list of scope strings.

    Args:
        scopes_json: JSON-encoded scope list.

    Returns:
        List of scope strings.
    """
    return json.loads(scopes_json)
