"""Per-purpose keys derived from the server ``SECRET_KEY``.

One secret must not key unrelated mechanisms: a signature or digest made for one purpose could then be
presented to another. Every purpose that signs or hashes with the server secret takes its own key from
here, an HMAC-SHA256 of the purpose name keyed by ``SECRET_KEY``, so the keys are independent of each
other and the secret itself is never used as a key. ``SECRET_KEY`` may list several secrets separated by commas,
like ``FERNET_KEY``: the first signs and every one verifies, so the secret can be rotated without signing everyone
out. Rotating ``SECRET_KEY`` rotates every derived key.
"""

import functools
import hashlib
import hmac
from typing import Final

import core.config as core_config

#: Signs and verifies access tokens.
JWT: Final = "jwt"

#: Signs and verifies refresh tokens. A key of its own, so an access token never verifies where a refresh token is
#: expected and the reverse, whatever its ``typ`` header says.
REFRESH_JWT: Final = "refresh-jwt"

#: Keys the digests of refresh tokens and CSRF tokens.
TOKEN_HMAC: Final = "token-hmac"  # noqa: S105 - purpose name, not a credential

#: Derives the raw emailed single-use tokens (password reset, sign-up and email change), so a digest kept for
#: lookup is never the value a mail carries.
EMAIL_TOKEN: Final = "email-token"  # noqa: S105 - purpose name, not a credential

#: Signs the capability URLs for photos, thumbnails and media.
CAPABILITY_URLS: Final = "capability-urls"


@functools.cache
def derive_keys(purpose: str) -> tuple[str, ...]:
    """Return the keys for a purpose, one per ``SECRET_KEY`` entry.

    Args:
        purpose: What the key is for; one of the purpose constants in this module.

    Returns:
        64-character hex keys in the order ``SECRET_KEY`` lists its secrets: the first signs, every one
        verifies. Empty when ``SECRET_KEY`` is not set.

    Raises:
        ValueError: If ``SECRET_KEY`` has an empty entry.
    """
    raw_secrets = core_config.read_secret("SECRET_KEY")
    if not raw_secrets:
        return ()
    return tuple(
        hmac.new(secret.encode(), f"endurain:{purpose}".encode(), hashlib.sha256).hexdigest()
        for secret in core_config.parse_key_list(raw_secrets, "SECRET_KEY")
    )


def derive_key(purpose: str) -> str | None:
    """Return the key that signs for a purpose.

    Args:
        purpose: What the key is for; one of the purpose constants in this module.

    Returns:
        A 64-character hex key (derived from the first ``SECRET_KEY`` entry), or ``None`` when ``SECRET_KEY`` is
        not set.
    """
    return next(iter(derive_keys(purpose)), None)
