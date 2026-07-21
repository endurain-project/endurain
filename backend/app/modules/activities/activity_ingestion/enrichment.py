"""Re-attach owner-scoped domain context to a freshly-parsed activity.

The file parsers (:mod:`modules.activities.activity_file_import`) are **pure** —
they derive only what the file bytes contain and never touch the DB, privacy
settings, gear, or Garmin (plan §18.2 / A7). This adapter seam re-attaches the
domain context the parsers used to resolve inline:

* the owner's **privacy defaults** (visibility + ``hide_*`` flags),
* the **gear id** (Garmin-synced gear for a Garmin import, else the user's
  default gear for the activity type),
* the **Garmin provider ids** on a Garmin sync.

Living in ``activity_ingestion`` (not the activities core) is what lets it import
``gears`` / ``users`` / ``garmin`` — the ``activities-parsing-boundary`` and the
``activity-file-import-purity`` import-linter contracts keep those imports out of
the core and the parsers respectively.
"""

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activities_schema
import modules.garmin.utils as garmin_utils
import modules.gears.gear.crud as gears_crud
import modules.users.users_default_gear.utils as user_default_gear_utils
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_privacy_settings.utils as users_privacy_settings_utils


def build_activity_privacy_kwargs(
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
) -> dict[str, bool | int]:
    """Build privacy field kwargs for an Activity from the owner's privacy settings.

    Args:
        user_privacy_settings: The activity owner's privacy-settings DTO.

    Returns:
        A dict of the ``visibility`` + ``hide_*`` fields ready to apply to an
        Activity.
    """
    ups = user_privacy_settings
    return {
        "visibility": users_privacy_settings_utils.visibility_to_int(ups.default_activity_visibility),
        "hide_start_time": ups.hide_activity_start_time or False,
        "hide_location": ups.hide_activity_location or False,
        "hide_map": ups.hide_activity_map or False,
        "hide_hr": ups.hide_activity_hr or False,
        "hide_power": ups.hide_activity_power or False,
        "hide_cadence": ups.hide_activity_cadence or False,
        "hide_elevation": ups.hide_activity_elevation or False,
        "hide_speed": ups.hide_activity_speed or False,
        "hide_pace": ups.hide_activity_pace or False,
        "hide_laps": ups.hide_activity_laps or False,
        "hide_workout_sets_steps": (ups.hide_activity_workout_sets_steps or False),
        "hide_gear": ups.hide_activity_gear or False,
    }


def resolve_gear_id(
    activity_type: int | None,
    user_id: int,
    db: Session,
    *,
    from_garmin: bool = False,
    garminconnect_gear: dict | None = None,
) -> int | None:
    """Resolve the gear id to associate with a parsed activity.

    Prefers the Garmin-synced gear (only when the import comes from Garmin, the
    user has gear sync enabled, and a matching gear exists), otherwise falls back
    to the user's default gear for the activity type.

    Args:
        activity_type: The parsed activity's sport-type code (may be ``None``).
        user_id: Owner user id.
        db: Database session.
        from_garmin: Whether the activity originates from a Garmin Connect sync.
        garminconnect_gear: Garmin gear metadata (``[{"uuid": ...}, ...]``) when
            available.

    Returns:
        The resolved gear id, or ``None`` when no gear applies.
    """
    gear_id: int | None = None
    if from_garmin and garminconnect_gear:
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)
        if user_integrations is not None and user_integrations.garminconnect_sync_gear:
            gear = gears_crud.get_gear_by_garminconnect_id_from_user_id(garminconnect_gear[0]["uuid"], user_id, db)
            if gear is not None:
                gear_id = gear.id
    if gear_id is None and activity_type is not None:
        gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(user_id, activity_type, db)
    return gear_id


def enrich_parsed_activity(
    activity: activities_schema.Activity,
    *,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
    db: Session,
    from_garmin: bool = False,
    garminconnect_gear: dict | None = None,
    garmin_connect_activity_id: int | None = None,
) -> None:
    """Populate owner privacy defaults, gear, and Garmin ids on a parsed activity in place.

    The parser produced a domain-free ``Activity`` (no privacy flags, gear, or
    provider ids); this fills those from the owner's context before persistence.

    Args:
        activity: The parsed activity to enrich (mutated in place).
        user_id: Owner user id.
        user_privacy_settings: The owner's privacy-settings DTO.
        db: Database session.
        from_garmin: Whether the activity originates from a Garmin Connect sync.
        garminconnect_gear: Garmin gear metadata, when available.
        garmin_connect_activity_id: The Garmin Connect activity id, for a Garmin
            sync.
    """
    for key, value in build_activity_privacy_kwargs(user_privacy_settings).items():
        setattr(activity, key, value)

    activity.gear_id = resolve_gear_id(
        activity.activity_type,
        user_id,
        db,
        from_garmin=from_garmin,
        garminconnect_gear=garminconnect_gear,
    )

    if from_garmin:
        activity.garminconnect_activity_id = garmin_connect_activity_id
        activity.garminconnect_gear_id = garminconnect_gear[0]["uuid"] if garminconnect_gear else None
