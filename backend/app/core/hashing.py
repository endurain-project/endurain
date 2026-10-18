"""Dependency-free hashing primitives shared across layers.

Holds the lowest-level hash helpers that both ``core`` infrastructure
(e.g. Redis key derivation) and higher layers (e.g. auth token hashing)
need. Keeping the primitive here — with no imports from ``core`` or
``auth`` — lets every layer depend on it downward without risking an
import cycle.
"""

import hashlib


def sha256_hex(value: str | bytes) -> str:
    """Return the SHA-256 hex digest of ``value``.

    Args:
        value: The string or byte payload to hash. Callers that need a
            canonical form (case-folding, normalization) must apply it
            before calling. Strings are encoded as UTF-8.

    Returns:
        Lowercase hex-encoded SHA-256 digest (64 chars).

    Raises:
        None.
    """
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def log_fingerprint(value: str) -> str:
    """Return a short one-way identifier for a secret-bearing value, for log lines.

    Logging any part of a session ID or OAuth state would hand a reader of the logs
    a prefix of a live credential. The fingerprint still lets one entry be matched
    with another about the same value, and cannot be turned back into it.

    Args:
        value: The identifier to fingerprint.

    Returns:
        The first 8 hex characters of the SHA-256 digest of ``value``.

    Raises:
        None.
    """
    return sha256_hex(value)[:8]
