"""Public, token-gated route that serves one activity media blob.

Intentionally **unauthenticated** (mounted without the activities auth
dependency) so it works in an ``<img src>`` tag; the capability is the signed
``t`` token minted by :mod:`signing`, which only the activity owner ever
receives, because the media list endpoint returns nothing for an activity the
caller does not own.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

import core.dependencies as core_dependencies
import core.http_cache as core_http_cache
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_media.service as activity_media_service

router = APIRouter()


@router.get(
    "/{activity_id}/media/{media_id}/file",
    responses={200: {"content": {"image/*": {}}}},
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_activity_media_file(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    media_id: core_dependencies.PositiveId,
    token: Annotated[str, Query(alias="t", description="Signed media access token")],
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> Response:
    """Serve an activity media blob when the signed token is valid.

    Answers ``404`` when the token is invalid or forged, the record does not belong
    to the activity, or no blob exists. A ``404`` rather than ``403`` avoids
    confirming the resource to an unauthorized caller.
    """
    data, content_type = activity_media_service.read_activity_media_blob(activity_id, media_id, token, storage, db)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": f"private, max-age={core_http_cache.SIGNED_URL_CACHE_MAX_AGE}"},
    )
