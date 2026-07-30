"""Signed, ``<img>``-compatible URLs for the token-gated thumbnail route.

Local activity thumbnails are no longer served from a public static mount at a
guessable path (``/activity_thumbnails/42.webp``). Instead the serialized
thumbnail URL carries an ``itsdangerous`` signature — keyed by the server
``SECRET_KEY`` and bound to the activity id — that the public thumbnail route
verifies before streaming the blob.

Why this shape:

* **The owner keeps their map.** The blob is never deleted on ``hide_map``; access
  is gated at serve time, not by removing data.
* **Non-owners cannot see a hidden map.** Visibility masking already strips the
  thumbnail URL from a non-owner's serialized activity, so they never *receive* a
  token; and because the token is signed with the server secret, they cannot
  *forge* one either.
* **Works in an ``<img src>`` tag.** The signature travels in the URL (a query
  param), so no ``Authorization`` header is required — the same capability-URL
  model object storage already uses for presigned URLs.

The token has no expiry so the URL is stable and browser-cacheable; its security
rests on being unforgeable and only ever handed to permitted viewers.
"""

import functools

from itsdangerous import BadData, URLSafeSerializer

import core.config as core_config

# Namespaces this signer from any other ``SECRET_KEY`` use (e.g. JWT signing).
_SALT = "activity-thumbnail"


@functools.lru_cache(maxsize=1)
def _serializer() -> URLSafeSerializer:
    """Return the process-wide thumbnail URL signer (secret read once)."""
    secret = core_config.read_secret("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured; cannot sign thumbnail URLs")
    return URLSafeSerializer(secret, salt=_SALT)


def sign_thumbnail_token(activity_id: int) -> str:
    """Return a signed token binding a thumbnail URL to ``activity_id``.

    Args:
        activity_id: The activity whose thumbnail the URL serves.

    Returns:
        An unforgeable, URL-safe token.
    """
    return _serializer().dumps(activity_id)


def verify_thumbnail_token(activity_id: int, token: str) -> bool:
    """Return whether ``token`` is a valid signature for ``activity_id``.

    Args:
        activity_id: The activity id the token must be bound to.
        token: The signed token from the request.

    Returns:
        True if the token is authentic and bound to ``activity_id``.
    """
    try:
        return _serializer().loads(token) == activity_id
    except BadData:
        return False
