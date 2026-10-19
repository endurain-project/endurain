"""Public activity stream endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_streams.dependencies as activity_streams_dependencies
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.service as activity_streams_service

router = APIRouter()


@router.get(
    "/streams",
    response_model=activity_streams_schema.ActivityStreamsPage,
)
def list_public_activity_streams(
    activity_id: activity_dependencies.ActivityId,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_streams_schema.ActivityStreamsPage:
    """Return one page of a publicly shared activity's streams, with the matching total."""
    return activity_streams_service.list_public_activity_streams(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.get(
    "/streams/{stream_type}",
    response_model=activity_streams_schema.ActivityStreamsRead,
)
def read_public_activity_stream(
    activity_id: activity_dependencies.ActivityId,
    stream_type: activity_streams_dependencies.StreamType,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_streams_schema.ActivityStreamsRead:
    """Get a public stream by type for an activity.

    Not found when the activity has no such stream, is not public, or public links
    are disabled. The cases are indistinguishable on purpose, since this endpoint
    is unauthenticated.
    """
    return activity_streams_service.get_public_activity_stream(activity_id, stream_type, db)
