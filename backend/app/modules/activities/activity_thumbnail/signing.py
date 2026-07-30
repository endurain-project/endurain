"""Address activity thumbnails: signed, ``<img>``-compatible URLs and their tokens.

Local activity thumbnails are not served from a public static mount at a
guessable path (``/activity_thumbnails/42.webp``). Instead the serialized
thumbnail URL carries a signature — keyed by the server ``SECRET_KEY`` and bound
to the activity id — that the public thumbnail route verifies before streaming
the blob. The signing primitive itself lives in :mod:`core.signing`; this module
owns the thumbnail-specific salt, the URL shape, and the storage backend choice.

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

The token is bounded by :data:`_TOKEN_MAX_AGE_SECONDS` rather than living forever:
an activity that was public (or ``hide_map``-off) when a viewer's page loaded can
later be hidden, and a token already handed out would otherwise still open the
blob until ``SECRET_KEY`` rotates. The window self-heals on every fresh view —
serializing the activity again mints a new token with a new timestamp — so this
only bounds how long a *previously issued* token survives a later visibility
change, without needing a revocation list. It is kept comfortably longer than the
route's own browser ``Cache-Control`` window (see ``activity_thumbnail.router``)
so a still-cached image never 404s mid-cache; this mirrors ``activity_media`` and
``users.users.signing``, which use the same policy for the same reason.

Addressing lives here rather than in ``render.py`` so serializing an activity does
not drag the rendering stack (staticmap, PIL) into the request path: the read path
only ever needs the URL, never the renderer.
"""

import core.config as core_config
import core.signing as core_signing
import infra.runtime as platform_runtime

# Namespaces this signer from any other ``SECRET_KEY`` use (e.g. JWT signing).
_SALT = "activity-thumbnail"

# How long a signed token remains valid after it was minted, bounding exposure
# after a later visibility change. Well past the route's 1-hour browser cache
# window so a cached image never expires mid-cache.
_TOKEN_MAX_AGE_SECONDS = 24 * 60 * 60

# The storage area (domain-owned namespace) activity thumbnails live under.
THUMBNAIL_STORAGE_AREA = "activity_thumbnails"


def thumbnail_key(activity_id: int) -> str:
    """Return the storage key for an activity's thumbnail (e.g. ``42.webp``)."""
    return f"{activity_id}.webp"


def sign_thumbnail_token(activity_id: int) -> str:
    """Return a signed token binding a thumbnail URL to ``activity_id``.

    Args:
        activity_id: The activity whose thumbnail the URL serves.

    Returns:
        An unforgeable, URL-safe token.
    """
    return core_signing.sign_token(_SALT, activity_id)


def verify_thumbnail_token(activity_id: int, token: str) -> bool:
    """Return whether ``token`` is a valid, unexpired signature for ``activity_id``.

    Args:
        activity_id: The activity id the token must be bound to.
        token: The signed token from the request.

    Returns:
        True if the token is authentic, bound to ``activity_id``, and no older
        than :data:`_TOKEN_MAX_AGE_SECONDS`.
    """
    return core_signing.verify_token(_SALT, activity_id, token, max_age=_TOKEN_MAX_AGE_SECONDS)


def thumbnail_url(key: str | None, activity_id: int) -> str | None:
    """Resolve a stored thumbnail to a signed, ``<img>``-compatible URL.

    Object storage keeps its presigned, expiring URL (already access-controlled
    and usable in an ``<img>`` tag). Local disk is served by the token-gated
    thumbnail route instead of a public static path, so the blob is only reachable
    with a valid signed token — minted here and handed only to permitted viewers
    via visibility masking, so a non-owner of a ``hide_map`` activity can neither
    receive nor forge one. The activity owner keeps their map.

    Args:
        key: The stored storage key, or ``None``.
        activity_id: The owning activity's id, bound into the signed token.

    Returns:
        A servable URL, or ``None`` when ``key`` is falsy.
    """
    if not key:
        return None
    # Object storage already serves via presigned, expiring, <img>-compatible
    # URLs; use them directly to avoid round-tripping every thumbnail through the
    # app.
    if core_config.settings.resolved_storage_uri.startswith("s3"):
        try:
            return platform_runtime.get_active_platform().storage.url(THUMBNAIL_STORAGE_AREA, key)
        except RuntimeError:
            pass
    # Local disk: a signed, token-gated app URL (no public static mount).
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/thumbnail?t={sign_thumbnail_token(activity_id)}"
