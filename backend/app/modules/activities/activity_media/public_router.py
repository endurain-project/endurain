"""Public, token-gated route that serves one activity media blob.

Intentionally **unauthenticated** (mounted without the activities auth
dependency) so it works in an ``<img src>`` tag; the capability is the signed
``t`` token minted by :mod:`signing`, which only the activity owner ever
receives, because the media list endpoint returns nothing for an activity the
caller does not own.
"""

from typing import Annotated

import jasil.providers as platform_providers
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_media.service as activity_media_service

router = APIRouter()

# Browser cache for the (stable, signed) media URL, in seconds.
_CACHE_MAX_AGE = 3600


@router.get(
    "/{activity_id}/media/{media_id}/file",
    responses={200: {"content": {"image/*": {}}}},
)
def read_activity_media_file(
    activity_id: activity_dependencies.ActivityId,
    media_id: core_dependencies.PositiveId,
    token: Annotated[str, Query(alias="t", description="Signed media access token")],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
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
        headers={"Cache-Control": f"private, max-age={_CACHE_MAX_AGE}"},
    )
