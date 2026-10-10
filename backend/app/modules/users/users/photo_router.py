"""Public, token-gated route that serves a user's profile photo.

Replaces the two unauthenticated paths this blob used to be reachable through: a
``StaticFiles`` mount over the user-images directory, and
``GET /user_images/{user_img}``. Both addressed the file as ``{user_id}.{ext}``,
so walking ``1.png``, ``2.png``, … enumerated every user's photo without
authenticating.

Intentionally **unauthenticated** so it works in an ``<img src>`` tag; the
capability is the signed ``t`` token minted by :mod:`signing` whenever a user
record is serialized. That deliberately allows any viewer who legitimately sees
the user — a follower, a feed reader, a visitor to a shared activity — to render
the avatar, while removing the ability to enumerate ids.
"""

from typing import Annotated

import jasil.runtime as platform_runtime
from fastapi import APIRouter, HTTPException, Query, Response, status

import core.logger as core_logger
import modules.users.users.signing as users_signing

logger = core_logger.get_logger(__name__)

router = APIRouter()

# Browser cache for the (stable, signed) photo URL, in seconds.
_CACHE_MAX_AGE = 3600

# Stored extensions, probed in turn because the row holds only the key the
# upload wrote and older rows may carry any allowed extension.
_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@router.get(
    "/{user_id}/photo",
    responses={200: {"content": {"image/*": {}}}},
)
def read_user_photo(
    user_id: int,
    token: Annotated[str, Query(alias="t", description="Signed photo access token")],
) -> Response:
    """Serve a user's profile photo when the signed token is valid.

    Args:
        user_id: The user whose photo to serve.
        token: The signed access token (``?t=``) minted at serialization time.

    Returns:
        The image bytes.

    Raises:
        HTTPException: 404 when the token is invalid/forged or no photo exists
            (a 404 — rather than 403 — avoids confirming the user id).
    """
    if not users_signing.verify_user_image_token(user_id, token):
        # Security-relevant: a forged token, or one replayed against another
        # user. Logged at warning so a probing pattern is visible.
        logger.warning(
            "Rejected a user photo request with an invalid signed token",
            extra=core_logger.context(user_id=user_id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User photo not found")

    storage = platform_runtime.get_active_platform().storage
    for extension, content_type in _CONTENT_TYPES.items():
        data = storage.get(users_signing.USER_IMAGE_STORAGE_AREA, f"{user_id}{extension}")
        if data is not None:
            return Response(
                content=data,
                media_type=content_type,
                headers={"Cache-Control": f"private, max-age={_CACHE_MAX_AGE}"},
            )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User photo not found")
