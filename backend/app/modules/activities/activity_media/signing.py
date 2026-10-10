"""Address activity media: signed, ``<img>``-compatible URLs and their tokens.

The counterpart of :mod:`modules.activities.activity_thumbnail.signing`, for the
same reason. Activity photos used to be served two ways at once — a public
``StaticFiles`` mount over the media directory *and* a public
``GET /activity_media/{media}`` route — both unauthenticated and both addressed
by a filename the client already held. Anyone who learned (or guessed) a stored
filename could fetch another athlete's photos, and the frontend had to reverse a
filesystem path into a URL to display its own.

Now the blob is reachable only through the token-gated route in
:mod:`modules.activities.activity_media.public_router`, and the capability is the
signed ``t`` token minted here. Media is owner-only (the list endpoint returns
nothing for an activity the caller does not own), so only the owner is ever
handed a token, and the server ``SECRET_KEY`` is what stops anyone else forging
one.

The token binds ``media_id`` alone; the route additionally checks the row belongs
to the ``activity_id`` in the path, so a URL cannot be replayed against another
activity. Its lifetime is :data:`core.signing.DEFAULT_TOKEN_MAX_AGE_SECONDS`,
shared with the thumbnail and user-photo signers.
"""

import core.signing as core_signing

# Namespaces this signer from any other ``SECRET_KEY`` use (e.g. JWT signing, and
# the activity-thumbnail signer): a media token can never be replayed as a
# thumbnail token even though both bind a bare integer id.
_SIGNER = core_signing.CapabilitySigner(salt="activity-media")

# The storage area (domain-owned namespace) activity media lives under. For the
# ``local`` backend this maps to ``{DATA_DIR}/activity_media`` — the exact
# directory the files were already written to — so existing installs keep their
# photos; for S3 it is the object key prefix.
MEDIA_STORAGE_AREA = "activity_media"


def sign_media_token(media_id: int) -> str:
    """Return a signed token binding a media URL to ``media_id``.

    Args:
        media_id: The media record the URL serves.

    Returns:
        An unforgeable, URL-safe token.
    """
    return _SIGNER.sign(media_id)


def verify_media_token(media_id: int, token: str) -> bool:
    """Return whether ``token`` is a valid, unexpired signature for ``media_id``.

    Args:
        media_id: The media id the token must be bound to.
        token: The signed token from the request.

    Returns:
        True if the token is authentic, bound to ``media_id``, and unexpired.
    """
    return _SIGNER.verify(media_id, token)


def media_url(key: str, activity_id: int, media_id: int) -> str:
    """Resolve a stored media key to a signed, ``<img>``-compatible URL.

    Args:
        key: The stored storage key.
        activity_id: The owning activity's id, which the route cross-checks.
        media_id: The media record's id, bound into the signed token.

    Returns:
        A servable URL.
    """
    return core_signing.blob_url(
        MEDIA_STORAGE_AREA,
        key,
        local_path=f"/activities/{activity_id}/media/{media_id}/file",
        token=sign_media_token(media_id),
    )
