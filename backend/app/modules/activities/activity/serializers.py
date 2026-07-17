"""ORM→schema serialization and visibility masking for activities.

Split out of ``utils.py``: the single place that turns an ``Activity`` ORM row
into the API ``Activity`` schema (applying timezone formatting and resolving the
stored thumbnail key to a servable URL) and that masks hidden fields for
non-owners. Consumed by ``crud`` at the ORM→schema boundary so ORM instances
never leave that layer.
"""

import core.timezone as core_timezone
import modules.activities.activity.models as activities_models
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_thumbnail.render as activity_thumbnail_render


def serialize_activity(
    activity: activities_models.Activity,
) -> activities_schema.Activity:
    """
    Convert an ORM Activity to a schema with TZ.

    Converts ORM model to Pydantic schema and
    applies timezone formatting to datetime fields.
    Does NOT mutate the ORM object.

    Args:
        activity: The ORM Activity instance.

    Returns:
        An Activity schema with formatted datetimes.
    """
    schema = activities_schema.Activity.model_validate(activity)

    # The DB stores the thumbnail's storage key; resolve it to a servable URL
    # (a same-origin path locally, or a presigned URL for object storage).
    schema.map_thumbnail_path = activity_thumbnail_render.thumbnail_url(activity.map_thumbnail_path)

    tz_name = activity.timezone
    schema.start_time_tz_applied = core_timezone.format_aware_datetime(activity.start_time, tz_name)
    schema.end_time_tz_applied = core_timezone.format_aware_datetime(activity.end_time, tz_name)
    schema.created_at_tz_applied = core_timezone.format_aware_datetime(activity.created_at, tz_name)

    schema.start_time = core_timezone.format_aware_datetime(activity.start_time, None)
    schema.end_time = core_timezone.format_aware_datetime(activity.end_time, None)
    schema.created_at = core_timezone.format_aware_datetime(activity.created_at, None)

    return schema


def apply_visibility_mask(
    schema: activities_schema.Activity,
    *,
    is_owner: bool,
    mask_private_notes: bool = True,
) -> activities_schema.Activity:
    """Mask hidden activity fields for non-owners.

    Mutates and returns the provided Pydantic schema instance.
    For owners no masking is applied.

    Args:
        schema: Activity schema to potentially mask.
        is_owner: Whether the requesting user owns the
            activity.
        mask_private_notes: Whether to clear private_notes
            for non-owners. Defaults to True.

    Returns:
        The (possibly mutated) Activity schema.
    """
    if is_owner:
        return schema
    if mask_private_notes:
        schema.private_notes = None
    if schema.hide_start_time:
        schema.start_time = None
        schema.end_time = None
    if schema.hide_location:
        schema.city = None
        schema.town = None
        schema.country = None
    if schema.hide_gear:
        schema.gear_id = None
        schema.strava_gear_id = None
        schema.garminconnect_gear_id = None
    return schema
