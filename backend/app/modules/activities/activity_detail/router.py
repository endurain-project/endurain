"""Authenticated route for the combined activity detail."""

from fastapi import APIRouter, Response, Security

import core.dependencies as core_dependencies
import core.etag as core_etag
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_detail.schema as activity_detail_schema
import modules.activities.activity_detail.service as activity_detail_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/detail",
    response_model=activity_detail_schema.ActivityDetailRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def read_activity_detail(
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> activity_detail_schema.ActivityDetailRead:
    """Return an activity with its laps, sets and workout steps in one read.

    Equivalent to reading the activity and each collection separately, with the access decision made
    once. Streams and media stay on their own routes. The ``ETag`` is the activity's, to echo in
    ``If-Match`` when saving it.
    """
    detail = activity_detail_service.get_activity_detail(activity_id, token_user_id, db)
    if detail.activity.version is not None:
        core_etag.set_etag(response, detail.activity.version)
    return detail
