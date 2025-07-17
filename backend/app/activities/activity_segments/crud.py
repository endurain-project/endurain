from datetime import date, datetime  # Added date
from urllib.parse import unquote

import activities.activity_streams.crud as streams_crud
import activities.activity_segments.schema as segments_schema
import activities.activity_segments.utils as segments_utils
import activities.activity_segments.models as segments_models
import core.logger as core_logger
import server_settings.crud as server_settings_crud
from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload

def get_all_segments(user_id: int, activity_type: int|None, db: Session):
    try:
        # Get the segments from the database, need to filter by user_id and activity_type.
        # Activity type can be None, in which case we return all segments for the user.

        if activity_type is None:
            segments = db.query(segments_models.Segment).filter(
                segments_models.Segment.user_id == user_id
                ).all()
        else:
            segments = db.query(segments_models.Segment).filter(
                segments_models.Segment.user_id == user_id,
                segments_models.Segment.activity_type == activity_type
                ).all()

        # Check if there are segments if not return None
        if not segments:
            return None

        # Return the segments
        return segments

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_segments: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err

def get_activity_segments(
        activity_id: int, user_id: int, db: Session
):
    core_logger.print_to_log(f"Getting segments for activity {activity_id}")

    # Returns the segments which correspond to the activity
    try:
        # Get the activity stream containing the GPS track from the database that corresponds to the activity_id
        stream = streams_crud.get_activity_stream_by_type(activity_id, 7, user_id, db)
        # Check if there is a GPS stream if not return None
        if not stream:
            return None

        # Get the segments from the database
        # TODO: Add filtering by activity_type
        segments = get_all_segments(user_id, None, db)

        # Check if there are segments if not return None
        if not segments:
            return None
        
        # Check for correspondence with returned segments
        corresponding_segments = []
        for segment in segments:
            if segments_utils.gps_trace_pass_all_gates(stream, segment):
                corresponding_segments.append(segment)
        
        # Return the segments
        return corresponding_segments
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_segments_by_activity_id: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err

def create_segment(
    segment: segments_schema.Segment, user_id: int, db: Session
) -> segments_schema.Segment:
    core_logger.print_to_log(f"Adding new segment to database")

    try:
        # Create a new segment
        new_segment = segments_utils.transform_schema_segment_to_model_segment(
            segment, user_id
        )

        # Add the segment to the database
        db.add(new_segment)
        db.commit()
        db.refresh(new_segment)

        segment.id = new_segment.id

        # Return the segment
        return segment

    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_segment: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
        
def edit_segment(db: Session):
    # TODO: Implement editing capability once UI elements / method's figured out!
    pass

def delete_segment(segment_id: int, db: Session):
    try:
        # Delete the segment
        num_deleted = (
            db.query(segments_models.Segment)
            .filter(segments_models.Segment.id == segment_id)
            .delete()
        )

        # Check if the segment was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segment with id {segment_id} not found",
            )

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_segment: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    pass

