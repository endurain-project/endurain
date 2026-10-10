"""The curated read interface other modules consume instead of the users internals.

Mirrors the pattern the activities module already exposes
(``activity/integration_service.py``) and the followers module established with
``list_accepted_followee_ids``: a consumer asks the owning module a question, it
never reaches into that module's CRUD, ORM or utility grab-bag.

Before this existed, activities imported ``users.users.utils``,
``users.users.crud``, ``users_privacy_settings.crud/utils`` and
``users_default_gear.utils`` directly — four entry points into another module's
internals, one of which (``users.users.utils``) also drags in FastAPI, the file-
upload helpers and the health-targets CRUD for callers that only wanted a
timezone. Narrowing it to the functions below is what lets the
``consumer-users-boundary`` import-linter contract hold the line.

Everything here returns schemas or primitives; no ORM row and no ``users``
internal type crosses the boundary.
"""

from datetime import date

from sqlalchemy.orm import Session

import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.utils as users_utils
import modules.users.users_default_gear.utils as users_default_gear_utils
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_privacy_settings.utils as users_privacy_settings_utils


def get_user(user_id: int, db: Session) -> users_schema.UsersRead | None:
    """Return a user by id, or ``None`` when there is no such user.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user record, or ``None``.
    """
    return users_crud.get_user_by_id(user_id, db)


def get_privacy_settings(user_id: int, db: Session) -> users_privacy_settings_schema.UsersPrivacySettingsRead | None:
    """Return a user's privacy settings, or ``None`` when they have none.

    Args:
        user_id: The owner whose defaults to read.
        db: Database session.

    Returns:
        The privacy settings, or ``None``.
    """
    return users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user_id, db)


def local_today(user_id: int, db: Session) -> date:
    """Return today's calendar date in the user's own timezone.

    "Which day is it?" is a local question the server cannot answer from its own
    clock, and the answer belongs to the users module because the timezone does.
    Consumers that bucket by day (activity summaries, week/month stats) resolve
    it here rather than reading ``users.timezone`` themselves.

    Args:
        user_id: The user whose "today" to resolve.
        db: Database session.

    Returns:
        The user's current calendar date.
    """
    return users_utils.user_local_today(user_id, db)


def timezone_or_default(timezone: str | None) -> str:
    """Return the given IANA timezone, or the server default when it is unset.

    ``users.timezone`` is nullable, so a consumer holding a user record still has
    to resolve the fallback; doing it here keeps the fallback rule in one place.

    Args:
        timezone: An IANA timezone name, or ``None``.

    Returns:
        An IANA timezone name.
    """
    return users_utils.timezone_or_default(timezone)


def default_visibility_to_int(
    visibility: str | users_privacy_settings_schema.ActivityVisibility | None,
) -> int:
    """Normalise a user's configured default activity visibility to its int code.

    Args:
        visibility: The stored privacy-settings visibility value.

    Returns:
        The integer visibility code (0=public, 1=followers, 2=private).
    """
    return users_privacy_settings_utils.visibility_to_int(visibility)


def get_default_gear_for_activity_type(user_id: int, activity_type: int, db: Session) -> int | None:
    """Return the user's default gear id for an activity type, if they set one.

    Args:
        user_id: The owning user.
        activity_type: The numeric sport type.
        db: Database session.

    Returns:
        The gear id, or ``None`` when the user has no default for this type.
    """
    return users_default_gear_utils.get_user_default_gear_by_activity_type(user_id, activity_type, db)
