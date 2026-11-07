"""Business operations for user integrations that run without a request."""

from sqlalchemy.orm import Session

import core.key_rotation as core_key_rotation
import modules.users.users_integrations.crud as user_integrations_crud


def reencrypt_stored_secrets(db: Session) -> None:
    """Re-encrypt the Strava and Garmin secrets under the first FERNET_KEY; does nothing while one key is configured.

    Args:
        db: SQLAlchemy database session.
    """
    core_key_rotation.reencrypt_in_batches(
        "users_integrations_strava",
        lambda after_id, limit: user_integrations_crud.stage_reencrypt_batch_strava(after_id, limit, db),
        db,
    )
    core_key_rotation.reencrypt_in_batches(
        "users_integrations_garmin",
        lambda after_id, limit: user_integrations_crud.stage_reencrypt_batch_garmin(after_id, limit, db),
        db,
    )
