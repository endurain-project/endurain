from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Tuple

import activities.activity_segments.schema as segments_schema
import activities.activity_segments.models as segments_models
import activities.activity_segments.crud as segments_crud
import activities.activity_segments.dependencies as segments_dependencies
import activities.activity.dependencies as activity_dependencies

import core.database as core_database
import core.dependencies as core_dependencies
import core.logger as core_logger

import session.security as session_security
import users.user.dependencies as users_dependencies

from fastapi import (
    Query
    )

# Define the API router
router = APIRouter()

@router.post(
    "",
    response_model=segments_schema.Segments,
    status_code=201,
)
async def create_segment(
    segment: segments_schema.Segments,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["segments:write"])
    ],
    user_id: Annotated[
        int, Depends(session_security.get_user_id_from_access_token)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # core_logger.print_to_log(segment)
    # Create the segment and return it
    return segments_crud.create_segment(segment, user_id, db)

@router.get(
    "/activity_id/{activity_id}/all",
    response_model=list[segments_schema.Segments] | None,
)
async def get_activity_segments(
        activity_id: int,
        check_scopes: Annotated[
            Callable, Security(session_security.check_scopes, scopes=["segments:read"])
        ],
        user_id: Annotated[
            int, Depends(session_security.get_user_id_from_access_token)
        ],
        db: Annotated[
            Session,
            Depends(core_database.get_db),
        ],
):
    # Return segments that correspond to the specified activity
    return segments_crud.get_segments_from_activity_segments_by_activity(activity_id, user_id, db)
    

@router.get(
    "/activity_id/{activity_id}/segment_id/{segment_id}/intersections",
    response_model=segments_schema.ActivitySegment | None,
)
async def get_activity_segment_intersections(
        activity_id: int,
        segment_id: int,
        check_scopes: Annotated[
            Callable, Security(session_security.check_scopes, scopes=["segments:read"])
        ],
        user_id: Annotated[
            int, Depends(session_security.get_user_id_from_access_token)
        ],
        db: Annotated[
            Session,
            Depends(core_database.get_db),
        ],
):
    # Return segments that correspond to the specified activity and segment
    return segments_crud.get_activity_segments_data_for_activity_by_segment(activity_id, segment_id, user_id, db)

@router.get(
    "/user/{user_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=List[segments_schema.Segments] | None,
)
async def read_segments_user_segments_pagination(
    user_id: int,
    valudate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["segments:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    validate_activity_type: Annotated[
        Callable, Depends(activity_dependencies.validate_activity_type)
    ],
    validate_sort_by: Annotated[
        Callable, Depends(segments_dependencies.validate_sort_by)
    ],
    validate_sort_order: Annotated[
        Callable, Depends(segments_dependencies.validate_sort_order)
    ],
    # Added optional filter query parameters
    activity_type: int | None = Query(None, alias="type"),
    name_search: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
):
    user_is_owner = True
    if token_user_id != user_id:
        user_is_owner = False
    # Get segments for the user with pagination and filters
    return segments_crud.get_user_segments_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        activity_type=activity_type,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
        user_is_owner=user_is_owner
    )

@router.get(
    "/types",
    response_model=dict | None,
)
async def read_segments_types(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["segments:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    return segments_crud.get_distinct_segment_types_for_user(token_user_id, db)

@router.get(
    "/number",
    response_model=int,
)
async def read_segments_user_segments_number(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["segments:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    validate_activity_type: Annotated[
        Callable, Depends(activity_dependencies.validate_activity_type)
    ],
    validate_sort_by: Annotated[
        Callable, Depends(segments_dependencies.validate_sort_by)
    ],
    validate_sort_order: Annotated[
        Callable, Depends(segments_dependencies.validate_sort_order)
    ],
    # Added optional filter query parameters
    activity_type: int | None = Query(None, alias="type"),
    name_search: str | None = Query(None),
):
    # Get the number of segments for the user
    segments = segments_crud.get_user_segments(
        user_id=token_user_id,
        db=db,
        activity_type=activity_type,
        name_search=name_search
    )

    # check if segments is None
    if segments is None:
        return 0
    
    # Return the number of segments
    return len(segments)

