"""ORM→schema serialization and visibility masking for activities.

Split out of ``utils.py``: the single place that turns an ``Activity`` ORM row
into the API ``Activity`` schema (resolving the stored thumbnail key to a
servable URL) and that masks hidden fields for non-owners. Consumed by ``crud``
at the ORM→schema boundary so ORM instances never leave that layer.

Datetimes cross the API as timezone-aware UTC instants, paired with the
activity's IANA ``timezone``; localizing for display is the client's job
(``Intl.DateTimeFormat`` with an explicit ``timeZone``). The server does not ship
pre-formatted wall clocks — those carried no offset, so their meaning depended on
server configuration, they could not be round-tripped, and they duplicated an
instant that then had to be masked in two places.
"""

import modules.activities.activity.models as activities_models
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_thumbnail.render as activity_thumbnail_render


def serialize_activity(
    activity: activities_models.Activity,
) -> activities_schema.Activity:
    """
    Convert an ORM Activity to its API schema.

    Does NOT mutate the ORM object.

    Args:
        activity: The ORM Activity instance.

    Returns:
        An Activity schema.
    """
    schema = activities_schema.Activity.model_validate(activity)

    # The DB stores the thumbnail's storage key; resolve it to a servable URL
    # (a signed, token-gated app route locally, or a presigned URL for object
    # storage). Visibility masking below strips this for non-owners of a hidden
    # map, so only permitted viewers ever receive the signed token.
    schema.map_thumbnail_path = activity_thumbnail_render.thumbnail_url(activity.map_thumbnail_path, activity.id)

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
        # One representation of the instant means one place to mask it.
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
    if schema.hide_map:
        # The map thumbnail is a rendered picture of the route, so hide_map must
        # suppress it for non-owners (the GPS map stream is masked separately via
        # is_stream_hidden). Without this a non-owner would still receive the
        # thumbnail URL in the serialized activity despite the privacy flag.
        schema.map_thumbnail_path = None
    return schema
