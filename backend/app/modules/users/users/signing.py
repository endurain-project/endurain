"""Address user profile photos: signed, ``<img>``-compatible URLs and their tokens.

The third and last blob kind to move off a public path, after activity
thumbnails and activity media. Profile photos were the worst of the three: the
stored filename is ``{user_id}.{ext}``, so ``/user_images/1.png``,
``/user_images/2.png``, … walked the entire user base with no authentication at
all. Both the ``StaticFiles`` mount and ``GET /user_images/{user_img}`` served
them.

The access model is deliberately looser than activity media, and matches how
avatars are actually used. A photo is not owner-only — it appears in a follower
list, an activity feed, and on a publicly shared activity — so the token is
minted whenever a user record is serialized, and anyone who legitimately receives
that record can render the image. What the token removes is *enumeration*: you
can no longer walk user ids, only fetch a photo you were handed a URL for.

The token is bounded by :data:`core.signing.DEFAULT_TOKEN_MAX_AGE_SECONDS` rather
than living forever: a photo removed or replaced stops being reachable under a
stale token within that window rather than for as long as ``SECRET_KEY`` is
unchanged.
"""

import core.signing as core_signing

# Namespaces this signer from the activity-thumbnail and activity-media signers,
# all of which bind a bare integer id.
_SIGNER = core_signing.CapabilitySigner(salt="user-image")

# Domain-owned storage namespace. For the ``local`` backend this maps to
# ``{DATA_DIR}/user_images`` — the directory the photos already live in — so an
# existing install needs no data migration; for S3 it is the object key prefix.
USER_IMAGE_STORAGE_AREA = "user_images"


def sign_user_image_token(user_id: int) -> str:
    """Return a signed token binding a photo URL to ``user_id``.

    Args:
        user_id: The user whose photo the URL serves.

    Returns:
        An unforgeable, URL-safe token.
    """
    return _SIGNER.sign(user_id)


def verify_user_image_token(user_id: int, token: str) -> bool:
    """Return whether ``token`` is a valid, unexpired signature for ``user_id``.

    Args:
        user_id: The user id the token must be bound to.
        token: The signed token from the request.

    Returns:
        True if the token is authentic, bound to ``user_id``, and unexpired.
    """
    return _SIGNER.verify(user_id, token)


def user_image_url(key: str | None, user_id: int | None) -> str | None:
    """Resolve a stored photo key to a signed, ``<img>``-compatible URL.

    Args:
        key: The stored storage key (``{user_id}.{ext}``), or ``None``.
        user_id: The owning user's id, bound into the signed token.

    Returns:
        A servable URL, or ``None`` when the user has no photo.
    """
    if not key or user_id is None:
        return None
    return core_signing.blob_url(
        USER_IMAGE_STORAGE_AREA,
        key,
        local_path=f"/users/{user_id}/photo",
        token=sign_user_image_token(user_id),
    )
