"""Public, token-gated route that serves a user's profile photo.

Replaces the two unauthenticated paths this blob used to be reachable through: a
``StaticFiles`` mount over the user-images directory, and
``GET /user_images/{user_img}``. Both addressed the file as ``{user_id}.{ext}``,
so walking ``1.png``, ``2.png``, … enumerated every user's photo without
authenticating.

Intentionally **unauthenticated** so it works in an ``<img src>`` tag; the
capability is the signed ``t`` token minted by ``signing`` whenever a user
record is serialized. That deliberately allows any viewer who legitimately sees
the user — a follower, a feed reader, a visitor to a shared activity — to render
the avatar, while removing the ability to enumerate ids.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

import core.dependencies as core_dependencies
import core.http_cache as core_http_cache
import core.rate_limit as core_rate_limit
import modules.users.users.photo_service as users_photo_service

router = APIRouter()


@router.get(
    "/{user_id}/photo",
    responses={200: {"content": {"image/*": {}}}},
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_user_photo(
    request: Request,
    user_id: core_dependencies.PositiveId,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
    token: Annotated[str, Query(alias="t", description="Signed photo access token")],
) -> Response:
    """Serve a user's profile photo when the signed token is valid.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: The user whose photo to serve.
        storage: The platform storage provider.
        db: Database session dependency.
        token: The signed access token (``?t=``) minted at serialization time.

    Returns:
        The image bytes.
    """
    data, content_type = users_photo_service.read_photo(user_id, token, storage, db)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": f"private, max-age={core_http_cache.SIGNED_URL_CACHE_MAX_AGE}"},
    )
