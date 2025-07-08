import activities.activity_segments.schema as segments_schema
import activities.activity_segments.utils as segments_utils
import activities.activity_segments.models as segments_models

def transform_schema_segment_to_model_segment(
    segment: segments_schema.Segment,
    user_id: int,
) -> segments_models.Segment:
    
    # Create a new segment object
    new_segment = segments_models.Segment(
        name=segment.name,
        user_id=user_id,
        activity_type=segment.activity_type,
        splits=segment.splits,
    )

    return new_segment
    