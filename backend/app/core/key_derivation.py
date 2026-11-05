"""Per-purpose keys derived from the server ``SECRET_KEY``.

One secret must not key unrelated mechanisms: a signature or digest made for one purpose could then be
presented to another. Every purpose that signs or hashes with the server secret takes its own key from
here, an HMAC-SHA256 of the purpose name keyed by ``SECRET_KEY``, so the keys are independent of each
other and the secret itself is never used as a key. Rotating ``SECRET_KEY`` rotates every derived key.
"""

import functools
import hashlib
import hmac
from typing import Final

import core.config as core_config

#: Signs and verifies access tokens.
JWT: Final = "jwt"

#: Keys the digests of refresh tokens and CSRF tokens.
TOKEN_HMAC: Final = "token-hmac"  # noqa: S105 - purpose name, not a credential

#: Derives the raw emailed single-use tokens (password reset, sign-up and email change), so a digest kept for
#: lookup is never the value a mail carries.
EMAIL_TOKEN: Final = "email-token"  # noqa: S105 - purpose name, not a credential

#: Signs the capability URLs for photos, thumbnails and media.
CAPABILITY_URLS: Final = "capability-urls"


@functools.cache
def derive_key(purpose: str) -> str | None:
    """Return the key for a purpose.

    Args:
        purpose: What the key is for; one of the purpose constants in this module.

    Returns:
        A 64-character hex key, or ``None`` when ``SECRET_KEY`` is not set.
    """
    secret = core_config.read_secret("SECRET_KEY")
    if not secret:
        return None
    return hmac.new(secret.encode(), f"endurain:{purpose}".encode(), hashlib.sha256).hexdigest()
