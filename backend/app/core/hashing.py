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
