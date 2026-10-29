"""Public, token-gated route that serves an activity's map thumbnail.

It is intentionally **unauthenticated** (mounted without the activities auth
dependency) so it can be used in an ``<img src>`` tag; the
capability is the signed ``t`` token minted by :mod:`signing` and handed only to
viewers permitted to see the map (visibility masking). A non-owner of a
``hide_map`` activity never receives a token and cannot forge one, so they cannot
fetch the blob — while the activity owner keeps their map.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

import core.dependencies as core_dependencies
import core.http_cache as core_http_cache
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_thumbnail.service as activity_thumbnail_service

router = APIRouter()


@router.get(
    "/{activity_id}/thumbnail",
    responses={200: {"content": {"image/webp": {}}}},
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_activity_thumbnail(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    token: Annotated[str, Query(alias="t", description="Signed thumbnail access token")],
    storage: core_dependencies.Storage,
) -> Response:
    """Serve an activity's map thumbnail when the signed token is valid.

    Answers ``404`` when the token is invalid or forged, or no thumbnail exists.
    """
    data = activity_thumbnail_service.read_activity_thumbnail(activity_id, token, storage)

    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": f"private, max-age={core_http_cache.SIGNED_URL_CACHE_MAX_AGE}"},
    )
