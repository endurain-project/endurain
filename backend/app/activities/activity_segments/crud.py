from urllib.parse import unquote

import activities.activity_streams.crud as streams_crud
import activities.activity_streams.models as streams_models
import activities.activity_segments.schema as segments_schema
import activities.activity_segments.utils as segments_utils
import activities.activity_segments.models as segments_models
import activities.activity.models as activities_models
import activities.activity.crud as activities_crud
import activities.activity.utils as activities_utils
import core.logger as core_logger
from fastapi import HTTPException, status
from sqlalchemy import func, or_, asc, desc
from sqlalchemy.orm import Session


def get_all_segments(user_id: int, activity_type: int | None, db: Session):
    try:
        if activity_type is None:
            segments = (
                db.query(segments_models.Segments)
                .filter(segments_models.Segments.user_id == user_id)
                .all()
            )
        else:
            segments = (
                db.query(segments_models.Segments)
                .filter(
                    segments_models.Segments.user_id == user_id,
                    segments_models.Segments.activity_type == activity_type,
                )
                .all()
            )

        # Check if there are segments if not return None
        if not segments:
            return None

        # Return the segments
        return segments
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_all_segments: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_segment_by_id(
    segment_id: int, user_id: int, db: Session
) -> segments_schema.Segments:
    try:
        # Get the segment from the database
        segment = (
            db.query(segments_models.Segments)
            .filter(
                segments_models.Segments.id == segment_id,
                segments_models.Segments.user_id == user_id,
            )
            .first()
        )

        # Check if the segment was found
        if not segment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Segment with id {segment_id} not found",
            )

        # Translate to schema
        schema_segment = segments_utils.transform_model_segment_to_schema_segment(
            segment
        )

        # Return the segment
        return schema_segment

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_segment_by_id: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_activity_segment_data_by_segment(
    segment_id: int, user_id: int, db: Session
) -> list[segments_schema.ActivitySegment] | None:
    try:
        activitySegmentResult = (
            db.query(segments_models.ActivitySegment)
            .filter_by(segment_id=segment_id)
            .order_by(asc(segments_models.ActivitySegment.start_time))
            .all()
        )

        if activitySegmentResult:
            activity_segments = []
            for activitySegment in activitySegmentResult:

                activityStreamLatLon = streams_crud.get_activity_stream_by_type(
                    activity_id=activitySegment.activity_id,
                    stream_type=7,
                    token_user_id=user_id,
                    db=db,
                )
                activityStreamEle = streams_crud.get_activity_stream_by_type(
                    activity_id=activitySegment.activity_id,
                    stream_type=6,
                    token_user_id=user_id,
                    db=db,
                )
                # Obtain timezone for the activity
                timezone = activities_crud.get_activity_timezone(
                    activitySegment.activity_id, db
                )

                gps_point_indexes = []
                for gps_point_index in activitySegment.gps_point_index_ordered:
                    gps_point_indexes.append((gps_point_index[0], gps_point_index[1]))
                gate_times = []
                for item in activitySegment.gate_times:
                    gate_times.append(
                        segments_utils.date_convert_timezone(item, timezone)
                    )
                activity_segment = {
                    "id": activitySegment.id,
                    "activity_id": activitySegment.activity_id,
                    "segment_id": activitySegment.segment_id,
                    "lap_number": activitySegment.lap_number,
                    "segment_name": activitySegment.segment_name.strip(),
                    "start_time": segments_utils.date_convert_timezone(
                        activitySegment.start_time, timezone
                    ),
                    "segment_ele_gain": activitySegment.segment_ele_gain,
                    "segment_ele_loss": activitySegment.segment_ele_loss,
                    "segment_pace": activitySegment.segment_pace,
                    "segment_hr_avg": activitySegment.segment_hr_avg,
                    "segment_hr_max": activitySegment.segment_hr_max,
                    "segment_distance": activitySegment.segment_distance,
                    "segment_time": activitySegment.segment_time,
                    "gate_ordered": activitySegment.gate_ordered,
                    "gate_times": gate_times,
                    "gps_point_index_ordered": gps_point_indexes,
                    "sub_segment_times": activitySegment.sub_segment_times,
                    "sub_segment_paces": activitySegment.sub_segment_paces,
                    "stream_latlon": activityStreamLatLon.stream_waypoints,
                    "stream_ele": activityStreamEle.stream_waypoints,
                }
                activity_segments.append(activity_segment)
            return activity_segments
        else:
            return None
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_activity_segment_data_by_segment: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_segments_data_for_activity_by_segment(
    activity_id: int, user_id: int, db: Session
):
    try:
        # Query all activity segments results for specified activity and segments
        activitySegmentResult = (
            db.query(segments_models.ActivitySegment)
            .filter_by(
                activity_id=activity_id,
            )
            .order_by(desc(segments_models.ActivitySegment.segment_time))
            .all()
        )
        if activitySegmentResult:
            activity_segments = []
            for activitySegment in activitySegmentResult:

                activityStreamLatLon = streams_crud.get_activity_stream_by_type(
                    activity_id=activitySegment.activity_id,
                    stream_type=7,
                    token_user_id=user_id,
                    db=db,
                )
                activityStreamEle = streams_crud.get_activity_stream_by_type(
                    activity_id=activitySegment.activity_id,
                    stream_type=6,
                    token_user_id=user_id,
                    db=db,
                )
                # Obtain timezone for the activity
                timezone = activities_crud.get_activity_timezone(
                    activitySegment.activity_id, db
                )

                gps_point_indexes = []
                for gps_point_index in activitySegment.gps_point_index_ordered:
                    gps_point_indexes.append((gps_point_index[0], gps_point_index[1]))
                gate_times = []
                for item in activitySegment.gate_times:
                    gate_times.append(
                        segments_utils.date_convert_timezone(item, timezone)
                    )
                activity_segment = {
                    "id": activitySegment.id,
                    "activity_id": activitySegment.activity_id,
                    "segment_id": activitySegment.segment_id,
                    "lap_number": activitySegment.lap_number,
                    "segment_name": activitySegment.segment_name.strip(),
                    "start_time": segments_utils.date_convert_timezone(
                        activitySegment.start_time, timezone
                    ),
                    "segment_ele_gain": activitySegment.segment_ele_gain,
                    "segment_ele_loss": activitySegment.segment_ele_loss,
                    "segment_pace": activitySegment.segment_pace,
                    "segment_hr_avg": activitySegment.segment_hr_avg,
                    "segment_hr_max": activitySegment.segment_hr_max,
                    "segment_distance": activitySegment.segment_distance,
                    "segment_time": activitySegment.segment_time,
                    "gate_ordered": activitySegment.gate_ordered,
                    "gate_times": gate_times,
                    "gps_point_index_ordered": gps_point_indexes,
                    "sub_segment_times": activitySegment.sub_segment_times,
                    "sub_segment_paces": activitySegment.sub_segment_paces,
                    "stream_latlon": activityStreamLatLon.stream_waypoints,
                    "stream_ele": activityStreamEle.stream_waypoints,
                }
                activity_segments.append(activity_segment)
            return activity_segments
        else:
            return None
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_segments_data_for_activity_by_segment: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_segments_from_calculation(activity_id: int, user_id: int, db: Session):
    core_logger.print_to_log(f"Getting segments for activity {activity_id}")

    # Returns the segments which correspond to the activity
    try:
        # Get the activity stream containing the GPS track from the database that corresponds to the activity_id
        activity = activities_crud.get_activity_by_id(activity_id=activity_id, db=db)
        stream = streams_crud.get_activity_stream_by_type(activity_id, 7, user_id, db)
        # Check if there is a GPS stream if not return None
        if not stream:
            return None

        # Get the segments from the database
        if activity:
            activity_type = activity.activity_type
        else:
            activity_type = None
        segments = get_all_segments(user_id, activity_type, db)

        # Check if there are segments if not return None
        if not segments:
            return None

        # Check for correspondence with returned segments
        corresponding_segments = []
        for segment in segments:
            intersections = segments_utils.gps_trace_gate_intersections(
                stream, segment, db
            )
            if intersections is not None:
                corresponding_segments.append(segment)

        # Return the segments
        return corresponding_segments
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_segments_from_calculation: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_segments_from_activity_segments_by_activity(
    activity_id: int, user_id: int, db: Session
):
    try:
        result = (
            db.query(segments_models.ActivitySegment)
            .filter_by(
                activity_id=activity_id,
            )
            .all()
        )
        segments = []
        for record in result:
            segmentresult = (
                db.query(segments_models.Segments).filter_by(id=record.segment_id).all()
            )
            for segment in segmentresult:
                segment.name = segment.name.strip()
            if not segmentresult[0] in segments:
                segments.append(segmentresult[0])
        return segments
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_segments_from_activity_segments_by_activity: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def add_activity_segments_from_new_segment(
    segment: segments_models.Segments, user_id: int, db: Session
):
    try:
        insert_segment_mappings = []
        # Check if this segment is passed thorugh by all of the users activities
        activities = activities_crud.get_user_activities(
            user_id, db, segment.activity_type
        )
        if activities:
            for activity in activities:
                activity_stream = streams_crud.get_activity_stream_by_type(
                    activity.id, 7, user_id, db
                )
                if activity_stream:
                    intersections = segments_utils.gps_trace_gate_intersections(
                        activity_stream, segment, db
                    )

                    segment_mappings = segments_utils.intersections_to_db_mapping(
                        intersections, activity, segment
                    )
                    if segment_mappings:
                        for db_mapping in segment_mappings:
                            insert_segment_mappings.append(db_mapping)

        if len(insert_segment_mappings) > 0:
            db.bulk_insert_mappings(
                segments_models.ActivitySegment, insert_segment_mappings
            )
            db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in add_activity_segments_from_new_segment: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def add_activity_segments_from_imported_activity(
    activity: activities_models.Activity,
    activity_stream: streams_models.ActivityStreams,
    db: Session,
):

    try:
        insert_segment_mappings = []

        # Check if this stream passes through any of the users segments
        if activity_stream.stream_type == 7:
            user_id = activity.user_id
            activity_type = activity.activity_type
            user_segments = get_all_segments(
                user_id=user_id, activity_type=activity_type, db=db
            )
            if user_segments:
                for segment in user_segments:
                    intersections = segments_utils.gps_trace_gate_intersections(
                        activity_stream, segment, db
                    )

                    segment_mappings = segments_utils.intersections_to_db_mapping(
                        intersections, activity, segment
                    )
                    if segment_mappings:
                        for db_mapping in segment_mappings:
                            insert_segment_mappings.append(db_mapping)

        if len(insert_segment_mappings) > 0:
            db.bulk_insert_mappings(
                segments_models.ActivitySegment, insert_segment_mappings
            )
            db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in add_activity_segments_from_imported_activity: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def refresh_segment_intersections_by_id(
    segment_id: int, user_id: int, db: Session
) -> bool:
    try:
        update_segment_mappings = []
        insert_segment_mappings = []

        segment = get_segment_by_id(segment_id=segment_id, user_id=user_id, db=db)
        activities = activities_crud.get_user_activities(
            user_id, db, segment.activity_type
        )
        if activities:
            for activity in activities:
                activity_stream = streams_crud.get_activity_stream_by_type(
                    activity.id, 7, user_id, db
                )
                if activity_stream:
                    intersections = segments_utils.gps_trace_gate_intersections(
                        activity_stream, segment, db
                    )

                    segment_mappings = segments_utils.intersections_to_db_mapping(
                        intersections, activity, segment
                    )

                    if segment_mappings:
                        for db_mapping in segment_mappings:
                            # Check if there's an existing record and update it. If not, create a new record
                            activitySegment = (
                                db.query(segments_models.ActivitySegment)
                                .filter_by(
                                    segment_id=db_mapping["segment_id"],
                                    activity_id=db_mapping["activity_id"],
                                    lap_number=db_mapping["lap_number"],
                                )
                                .first()
                            )
                            if activitySegment:
                                db_mapping["id"] = activitySegment.id
                                update_segment_mappings.append(db_mapping)
                            else:
                                insert_segment_mappings.append(db_mapping)
        if len(insert_segment_mappings) > 0:
            db.bulk_insert_mappings(
                segments_models.ActivitySegment, insert_segment_mappings
            )
            db.commit()
        if len(update_segment_mappings) > 0:
            db.bulk_update_mappings(
                segments_models.ActivitySegment, update_segment_mappings
            )
            db.commit()
        return True
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in refresh_segment_intersections_by_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_user_segments_for_activity_stream(
    activity_stream, activity_type: int, user_id: int, db: Session
):
    try:
        # Get all user segments that correspond with the activity
        # Returns a list of segment_id's
        segment_ids = []
        if activity_stream:
            user_segments = (
                db.query(segments_models.Segments)
                .filter_by(user_id=user_id, activity_type=activity_type)
                .all()
            )

            for segment in user_segments:
                intersections = segments_utils.gps_trace_gate_intersections(
                    activity_stream, segment, db
                )
                if intersections:
                    segment_ids.append(segment.id)

        return segment_ids
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_user_segments_for_activity_stream: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_user_segments_for_activity(
    activity_id: int, activity_type: int, user_id: int, db: Session
):
    try:
        # Get all user segments that correspond with the activity
        # Returns a list of segment_id's

        activity_stream = streams_crud.get_activity_stream_by_type(
            activity_id=activity_id,
            stream_type=7,
            token_user_id=user_id,
            db=db,
        )
        segment_ids = []
        if activity_stream:
            user_segments = (
                db.query(segments_models.Segments)
                .filter_by(user_id=user_id, activity_type=activity_type)
                .all()
            )

            for segment in user_segments:
                intersections = segments_utils.gps_trace_gate_intersections(
                    activity_stream, segment, db
                )
                if intersections:
                    segment_ids.append(segment.id)

        return segment_ids
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_user_segments_for_activity: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_user_activities_for_segment(
    segment: segments_schema.Segments, user_id: int, db: Session
):
    try:
        # Get all user activities that correspond with the segment
        # Returns a tuple with the list of activity_id's and the datetime of the most recent activity

        user_activities = activities_crud.get_user_activities(
            user_id=user_id, db=db, activity_type=segment.activity_type
        )

        activity_ids = []
        activity_dates = []
        for activity in user_activities:
            activity_stream = streams_crud.get_activity_stream_by_type(
                activity_id=activity.id,
                stream_type=7,
                token_user_id=user_id,
                db=db,
            )
            if activity_stream:
                intersections = segments_utils.gps_trace_gate_intersections(
                    activity_stream, segment, db
                )
                if intersections:
                    activity_ids.append(activity.id)
                    activity_dates.append(activity.start_time)
        activity_dates.sort()

        return (activity_ids, activity_dates[-1])
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_user_activities_for_segment: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_segment(
    segment: segments_schema.Segments, user_id: int, db: Session
) -> segments_schema.Segments:
    core_logger.print_to_log(f"Adding new segment to database")

    try:
        # Create a new segment
        new_segment = segments_utils.transform_schema_segment_to_model_segment(
            segment, user_id
        )

        db.expunge_all()

        # Add the segment to the segments table
        db.add(new_segment)
        db.commit()
        db.refresh(new_segment)

        segment.id = new_segment.id

        # Check all user activities to determine which pass through the newly defined segment, and add to the activity_segment table
        add_activity_segments_from_new_segment(segment, user_id, db)

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
        db.expunge_all()

        # Delete the segment
        num_deleted = (
            db.query(segments_models.Segments)
            .filter(segments_models.Segments.id == segment_id)
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


def get_user_segments(
    user_id: int,
    db: Session,
    activity_type: int | None = None,
    name_search: str | None = None,
) -> list[segments_models.Segments] | None:
    try:
        # Base query
        query = db.query(segments_models.Segments).filter(
            segments_models.Segments.user_id == user_id
        )

        # Apply filters
        if activity_type:
            query = query.filter(
                segments_models.Segments.activity_type == activity_type
            )

        if name_search:
            # Decode and prepare search term
            search_term = unquote(name_search).replace("+", " ").lower()
            # Apply search across name, town, city, and country
            query = query.filter(
                or_(
                    func.lower(segments_models.Segments.name).like(f"%{search_term}%"),
                    func.lower(segments_models.Segments.town).like(f"%{search_term}%"),
                    func.lower(segments_models.Segments.city).like(f"%{search_term}%"),
                    func.lower(segments_models.Segments.country).like(
                        f"%{search_term}%"
                    ),
                )
            )

        segments = query.all()

        # Check if there are segments
        if not segments:
            return None

        return segments
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_segments: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_segments_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
    activity_type: int | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    user_is_owner: bool = False,
) -> list[segments_models.Segments] | None:
    # core_logger.print_to_log(f"Getting segments for user {user_id} with pagination")
    try:
        # Mapping from frontend sort keys to database model fields
        SORT_MAP = {
            "type": segments_models.Segments.activity_type,
            "name": segments_models.Segments.name,
            "num_activities": func.count(segments_models.ActivitySegment.id),
            "most_recent_activity": func.max(
                segments_models.ActivitySegment.start_time
            ),
        }

        # Base query
        query = (
            db.query(
                segments_models.Segments,
                func.count(segments_models.ActivitySegment.id).label("num_activities"),
                func.max(segments_models.ActivitySegment.start_time).label(
                    "most_recent_activity"
                ),
            )
            .join(
                segments_models.ActivitySegment,
                segments_models.Segments.id
                == segments_models.ActivitySegment.segment_id,
            )
            .group_by(
                segments_models.Segments.id,
                segments_models.Segments.user_id,
                segments_models.Segments.name,
                segments_models.Segments.activity_type,
                segments_models.Segments.city,
                segments_models.Segments.town,
                segments_models.Segments.country,
            )
            .filter(segments_models.Segments.user_id == user_id)
        )

        # Apply filters
        if activity_type:
            query = query.filter(
                segments_models.Segments.activity_type == activity_type
            )

        if name_search:
            # Decode and prepare search term
            search_term = unquote(name_search).replace("+", " ").lower()
            # Apply search across name, town, city, and country
            query = query.filter(
                or_(
                    func.lower(segments_models.Segments.name).like(f"%{search_term}%"),
                    func.lower(segments_models.Segments.town).like(f"%{search_term}%"),
                    func.lower(segments_models.Segments.city).like(f"%{search_term}%"),
                    func.lower(segments_models.Segments.country).like(
                        f"%{search_term}%"
                    ),
                )
            )

        # Apply sorting
        sort_ascending = sort_order and sort_order.lower() == "asc"

        if sort_by == "location":
            # Special handling for location: sort by country, then city, then town
            # Handle nulls by using COALESCE with a maximum value for DESC or minimum value for ASC
            if sort_ascending:
                query = query.order_by(
                    func.coalesce(segments_models.Segments.country, "").asc(),
                    func.coalesce(segments_models.Segments.city, "").asc(),
                    func.coalesce(segments_models.Segments.town, "").asc(),
                )
            else:
                query = query.order_by(
                    func.coalesce(segments_models.Segments.country, "").desc(),
                    func.coalesce(segments_models.Segments.city, "").desc(),
                    func.coalesce(segments_models.Segments.town, "").desc(),
                )
        else:
            #     # Standard sorting for other columns
            sort_column = SORT_MAP.get(
                sort_by, func.max(segments_models.ActivitySegment.start_time)
            )

            # For numeric columns, use COALESCE with a very small/large number
            if sort_column in [
                func.count(segments_models.ActivitySegment.id),
            ]:
                if sort_ascending:
                    query = query.order_by(func.coalesce(sort_column, -999999).asc())
                else:
                    query = query.order_by(func.coalesce(sort_column, -999999).desc())
            # For string/date columns
            else:
                if sort_ascending:
                    query = query.order_by(sort_column.asc())
                else:
                    query = query.order_by(sort_column.desc())

        # # Apply pagination
        paginated_query = query.offset((page_number - 1) * num_records).limit(
            num_records
        )

        result = paginated_query.all()

        segments = []
        for segment, num_activities, most_recent_activity in result:
            # timezone = activities_crud.get_activity_by_id(activity_id=activity_id, db=db).timezone
            segment.num_activities = num_activities
            segment.most_recent_activity = segments_utils.date_convert_timezone(
                most_recent_activity, None
            )
            segments.append(segment)

        # Return the segments
        return segments if segments else None

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_segments_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_distinct_segment_types_for_user(user_id: int, db: Session):
    try:
        # Query distinct activity types (ID) for segments of the user
        type_ids = (
            db.query(segments_models.Segments.activity_type)
            .filter(segments_models.Segments.user_id == user_id)
            .distinct()
            .order_by(segments_models.Segments.activity_type)
            .all()
        )

        # Map type IDs to names, exculding None values
        return {
            type_id: activities_utils.ACTIVITY_ID_TO_NAME.get(type_id, "Unknown")
            for type_id, in type_ids
            if type_id is not None
        }
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_distinct_segment_types_for_user: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
