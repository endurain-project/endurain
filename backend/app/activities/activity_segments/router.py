from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Security
from sqlalchemy.orm import Session

import session.security as session_security

import activities.activity_segments.schema as segments_schema
import activities.activity_segments.crud as segments_crud

import core.database as core_database

# Define the API router
router = APIRouter()

@router.post(
    "",
    response_model=segments_schema.Segment,
    status_code=201,
)
async def create_segment(
    segment: segments_schema.Segment,
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
    # Create the segment and return it
    return segments_crud.create_segment(segment, user_id, db)

