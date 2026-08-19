"""ORM↔schema transformation and visibility masking for activities.

The single place that maps between the ``Activity`` ORM row and the API
``Activity`` schema, in both directions: serializing a row (resolving the stored
thumbnail key to a servable URL), masking the fields a non-owner may not see, and
building the row a write persists. ``crud`` calls these at its edges, so ORM
instances never leave the persistence layer and no other file needs to know the
field-by-field mapping.

Datetimes cross the API as timezone-aware UTC instants, paired with the
activity's IANA ``timezone``; localizing for display is the client's job
(``Intl.DateTimeFormat`` with an explicit ``timeZone``). The server does not ship
pre-formatted wall clocks — those carried no offset, so their meaning depended on
server configuration, they could not be round-tripped, and they duplicated an
instant that then had to be masked in two places.
"""

from sqlalchemy import func

import core.sanitization as core_sanitization
import core.timezone as core_timezone
import modules.activities.activity.models as activities_models
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing


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
    schema.map_thumbnail_path = activity_thumbnail_signing.thumbnail_url(activity.map_thumbnail_path, activity.id)

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


def serialize_and_mask(
    activities: list[activities_models.Activity],
    *,
    requester_user_id: int | None = None,
    force_non_owner: bool = False,
    mask_private_notes: bool = True,
) -> list[activities_schema.Activity]:
    """Serialize ORM rows and apply visibility masking.

    Args:
        activities: ORM Activity rows.
        requester_user_id: ID of requesting user; treated as
            owner when matches the row's user_id. Ignored when
            ``force_non_owner`` is True.
        force_non_owner: When True, every row is masked as if
            the requester is not the owner.
        mask_private_notes: Whether to mask ``private_notes``
            for non-owners.

    Returns:
        List of Activity schema instances with visibility
        masking applied.
    """
    result: list[activities_schema.Activity] = []
    for orm_activity in activities:
        schema = serialize_activity(orm_activity)
        is_owner = not force_non_owner and requester_user_id is not None and orm_activity.user_id == requester_user_id
        apply_visibility_mask(
            schema,
            is_owner=is_owner,
            mask_private_notes=mask_private_notes,
        )
        result.append(schema)
    return result


def deserialize_activity(
    activity: activities_schema.ActivityBase,
) -> activities_models.Activity:
    """Build the ORM row a write persists from its API schema.

    Args:
        activity: The activity to persist.

    Returns:
        An unpersisted ORM Activity, not yet added to a session.
    """
    # Use an explicit UTC-aware created_at when provided,
    # otherwise let the database stamp the row with now().
    created_date = core_timezone.to_utc_aware(activity.created_at) if activity.created_at is not None else func.now()

    # Sanitize markdown fields to prevent XSS
    sanitized_description = core_sanitization.sanitize_markdown(activity.description)
    sanitized_private_notes = core_sanitization.sanitize_markdown(activity.private_notes)

    # Create a new activity object
    new_activity = activities_models.Activity(
        user_id=activity.user_id,
        description=sanitized_description,
        private_notes=sanitized_private_notes,
        distance=activity.distance,
        name=activity.name,
        activity_type=activity.activity_type,
        start_time=core_timezone.to_utc_aware(activity.start_time),
        end_time=core_timezone.to_utc_aware(activity.end_time),
        timezone=activity.timezone,
        total_elapsed_time=activity.total_elapsed_time,
        total_timer_time=(
            activity.total_timer_time if activity.total_timer_time is not None else activity.total_elapsed_time
        ),
        city=activity.city,
        town=activity.town,
        country=activity.country,
        created_at=created_date,
        elevation_gain=activity.elevation_gain,
        elevation_loss=activity.elevation_loss,
        pace=activity.pace,
        average_speed=activity.average_speed,
        max_speed=activity.max_speed,
        average_power=activity.average_power,
        max_power=activity.max_power,
        normalized_power=activity.normalized_power,
        average_hr=activity.average_hr,
        max_hr=activity.max_hr,
        average_cad=activity.average_cad,
        max_cad=activity.max_cad,
        workout_feeling=activity.workout_feeling,
        workout_rpe=activity.workout_rpe,
        calories=activity.calories,
        visibility=activity.visibility,
        gear_id=activity.gear_id,
        strava_gear_id=activity.strava_gear_id,
        strava_activity_id=activity.strava_activity_id,
        garminconnect_activity_id=activity.garminconnect_activity_id,
        garminconnect_gear_id=activity.garminconnect_gear_id,
        import_info=activity.import_info,
        is_hidden=activity.is_hidden if activity.is_hidden is not None else False,
        hide_start_time=activity.hide_start_time,
        hide_location=activity.hide_location,
        hide_map=activity.hide_map,
        hide_hr=activity.hide_hr,
        hide_power=activity.hide_power,
        hide_cadence=activity.hide_cadence,
        hide_elevation=activity.hide_elevation,
        hide_speed=activity.hide_speed,
        hide_pace=activity.hide_pace,
        hide_laps=activity.hide_laps,
        hide_workout_sets_steps=activity.hide_workout_sets_steps,
        hide_gear=activity.hide_gear,
        tracker_manufacturer=activity.tracker_manufacturer,
        tracker_model=activity.tracker_model,
        total_cycles=activity.total_cycles,
    )

    return new_activity
