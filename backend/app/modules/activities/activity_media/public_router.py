"""Public, token-gated route that serves one activity media blob.

Replaces the two unauthenticated paths this file used to be reachable through: a
``StaticFiles`` mount over the media directory, and a ``GET /activity_media/{media}``
route. Both were addressed by the stored filename, so anyone who learned one
could fetch another athlete's photos.

Intentionally **unauthenticated** (mounted without the activities auth
dependency) so it works in an ``<img src>`` tag; the capability is the signed
``t`` token minted by :mod:`signing`, which only the activity owner ever
receives, because the media list endpoint returns nothing for an activity the
caller does not own.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import modules.activities.activity_media.service as activity_media_service
import modules.activities.activity_media.signing as activity_media_signing

logger = core_logger.get_logger(__name__)

router = APIRouter()

# Browser cache for the (stable, signed) media URL, in seconds.
_CACHE_MAX_AGE = 3600


@router.get(
    "/{activity_id}/media/{media_id}/file",
    responses={200: {"content": {"image/*": {}}}},
)
def read_activity_media_file(
    activity_id: int,
    media_id: int,
    token: Annotated[str, Query(alias="t", description="Signed media access token")],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> Response:
    """Serve an activity media blob when the signed token is valid.

    Args:
        activity_id: The activity the media must belong to.
        media_id: The media record to serve.
        token: The signed access token (``?t=``) minted at serialization time.
        db: Database session dependency.

    Returns:
        The image bytes.

    Raises:
        HTTPException: 404 when the token is invalid/forged, the record does not
            belong to ``activity_id``, or no blob exists (a 404 — rather than
            403 — avoids confirming the resource to an unauthorized caller).
    """
    if not activity_media_signing.verify_media_token(media_id, token):
        # Security-relevant: either a forged token or one replayed against a
        # different media id. Logged at warning so a probing pattern is visible.
        logger.warning(
            "Rejected an activity media request with an invalid signed token",
            extra=core_logger.context(activity_id=activity_id, media_id=media_id),
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity media not found")

    blob = activity_media_service.read_activity_media_blob(activity_id, media_id, db)
    if blob is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity media not found")

    data, content_type = blob
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": f"private, max-age={_CACHE_MAX_AGE}"},
    )
