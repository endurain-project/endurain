"""Re-attach owner-scoped domain context to a freshly-parsed activity.

The file parsers (:mod:`modules.activities.activity_file_import`) are **pure** —
they derive only what the file bytes contain and never touch the DB, privacy
settings or gear. This adapter seam re-attaches the domain context the parsers
used to resolve inline:

* the owner's **privacy defaults** (visibility + ``hide_*`` flags),
* the **gear id** — whatever the source already resolved, else the user's
  default gear for the activity type,
* the **provider ids** on a provider sync.

It resolves no *provider* gear itself. Doing so meant importing
``modules.garmin`` to check the sync flag and ``modules.gears`` to look the gear
up, which put a provider on the inbound side of the activities module. The
provider knows it is a provider: it resolves its own gear and hands ingestion the
id, so this seam only has to answer "and if not, what is the default?".
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.contracts as activities_contracts
import modules.users.users.integration_service as users_integration_service
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema

logger = core_logger.get_logger(__name__)


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
        "visibility": users_integration_service.default_visibility_to_int(ups.default_activity_visibility),
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
    provider_gear_id: int | None = None,
) -> int | None:
    """Resolve the gear id to associate with a parsed activity.

    Prefers the gear the source already resolved (a provider sync matching its
    own synced gear), otherwise falls back to the user's default gear for the
    activity type.

    Args:
        activity_type: The parsed activity's sport-type code (may be ``None``).
        user_id: Owner user id.
        db: Database session.
        provider_gear_id: Gear id the source resolved, when it had one.

    Returns:
        The resolved gear id, or ``None`` when no gear applies.
    """
    gear_id = provider_gear_id
    if gear_id is None and activity_type is not None:
        gear_id = users_integration_service.get_default_gear_for_activity_type(user_id, activity_type, db)
    logger.debug(
        "Resolved gear for a parsed activity",
        extra=core_logger.context(
            user_id=user_id,
            activity_type=activity_type,
            gear_id=gear_id,
            from_provider=provider_gear_id is not None,
        ),
    )
    return gear_id


def enrich_parsed_activity(
    activity: activities_contracts.ActivityCore,
    *,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
    db: Session,
    from_garmin: bool = False,
    provider_gear_id: int | None = None,
    garminconnect_gear_id: str | None = None,
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
        provider_gear_id: Gear id the source resolved, when it had one.
        garminconnect_gear_id: The Garmin Connect gear UUID recorded on the
            activity, for a Garmin sync.
        garmin_connect_activity_id: The Garmin Connect activity id, for a Garmin
            sync.
    """
    for key, value in build_activity_privacy_kwargs(user_privacy_settings).items():
        setattr(activity, key, value)

    activity.gear_id = resolve_gear_id(
        activity.activity_type,
        user_id,
        db,
        provider_gear_id=provider_gear_id,
    )

    if from_garmin:
        activity.garminconnect_activity_id = garmin_connect_activity_id
        activity.garminconnect_gear_id = garminconnect_gear_id
        logger.debug(
            "Attached Garmin provider ids to a parsed activity",
            extra=core_logger.context(
                user_id=user_id,
                garminconnect_activity_id=garmin_connect_activity_id,
            ),
        )

    logger.debug(
        "Enriched a parsed activity with owner context",
        extra=core_logger.context(
            user_id=user_id,
            visibility=activity.visibility,
            gear_id=activity.gear_id,
        ),
    )
