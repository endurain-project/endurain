"""Public, token-gated route that serves an activity's map thumbnail.

This route replaces the public static mount that used to serve thumbnails at a
guessable path. It is intentionally **unauthenticated** (mounted without the
activities auth dependency) so it can be used in an ``<img src>`` tag; the
capability is the signed ``t`` token minted by :mod:`signing` and handed only to
viewers permitted to see the map (visibility masking). A non-owner of a
``hide_map`` activity never receives a token and cannot forge one, so they cannot
fetch the blob — while the activity owner keeps their map.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

import core.logger as core_logger
import infra.runtime as platform_runtime
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing

logger = core_logger.get_logger(__name__)

router = APIRouter()

# Browser cache for the (stable, signed) thumbnail URL, in seconds.
_CACHE_MAX_AGE = 3600


@router.get(
    "/{activity_id}/thumbnail",
    responses={200: {"content": {"image/webp": {}}}},
)
def read_activity_thumbnail(
    activity_id: int,
    token: Annotated[str, Query(alias="t", description="Signed thumbnail access token")],
) -> Response:
    """Serve an activity's map thumbnail when the signed token is valid.

    Args:
        activity_id: The activity whose thumbnail to serve.
        token: The signed access token (``?t=``) minted at serialization time.

    Returns:
        The WebP thumbnail bytes.

    Raises:
        HTTPException: 404 when the token is invalid/forged or no thumbnail
            exists (a 404 — rather than 403 — avoids confirming the resource to
            an unauthorized caller).
    """
    if not activity_thumbnail_signing.verify_thumbnail_token(activity_id, token):
        # Security-relevant: either a forged token or one replayed against a
        # different activity. Logged at warning so a probing pattern is visible.
        logger.warning(
            "Rejected a thumbnail request with an invalid signed token",
            extra=core_logger.context(activity_id=activity_id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")

    storage = platform_runtime.get_active_platform().storage
    data = storage.get(
        activity_thumbnail_signing.THUMBNAIL_STORAGE_AREA,
        activity_thumbnail_signing.thumbnail_key(activity_id),
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found")

    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": f"private, max-age={_CACHE_MAX_AGE}"},
    )
