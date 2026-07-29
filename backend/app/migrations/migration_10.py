"""Migration 10: move user profile photos behind the ``StorageProvider``.

Photos were written to a configured user-images directory and the absolute
filesystem path was stored on the row, which is also how the removed public mount
and ``GET /user_images/{user_img}`` addressed them. Because the stored name is
``{user_id}.{ext}``, that path enumerated every user's photo without
authentication.

They are now stored through the platform ``StorageProvider`` under the
``user_images`` area, keyed by that same bare filename, and served only via the
token-gated route.

The ``local`` backend maps the area to ``{DATA_DIR}/user_images`` — the directory
the files already occupy — so a self-host install copies nothing: only the DB
value is rewritten from the absolute path to the key. Installs configured for
object storage additionally have the bytes uploaded. A row whose file is missing
has its photo cleared, because it can no longer resolve to anything servable.
Legacy values are recognised by containing a path separator; keys never do, so
the migration is idempotent.
"""

import os
from pathlib import Path

from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import infra.runtime as platform_runtime
import migrations.crud as migrations_crud
import modules.users.users.crud as users_crud
import modules.users.users.signing as users_signing

logger = core_logger.get_logger(__name__)


def _user_image_area_dir() -> Path:
    """Return the local directory the user-image storage area maps to.

    Derived from the ``StorageProvider`` area convention (``{DATA_DIR}/{area}``)
    rather than a setting, so there is one definition of where a local photo
    lives.
    """
    return Path(core_config.settings.DATA_DIR).resolve() / users_signing.USER_IMAGE_STORAGE_AREA


def _legacy_file(photo_path: str) -> Path | None:
    """Resolve a legacy photo path to an existing file inside the image directory.

    Args:
        photo_path: The stored path.

    Returns:
        The resolved file, or ``None`` when it is missing or escapes the area.
    """
    base = _user_image_area_dir()
    candidate = Path(photo_path.replace("\\", "/"))
    # Migrations 4 and 5 rewrote these paths twice (``data/`` then
    # ``/app/backend/``), neither of which resolves on a host install, so fall
    # back to the basename inside the area.
    for resolved in (candidate, base / candidate.name):
        try:
            full = resolved.resolve()
        except OSError:
            continue
        if full.is_file() and full.is_relative_to(base):
            return full
    return None


def process_migration_10(db: Session) -> None:
    """Rewrite legacy user photo paths to ``StorageProvider`` keys.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None.
    """
    logger.info("Started migration 10", extra=core_logger.context(console=True))

    storage = platform_runtime.get_active_platform().storage
    is_local = not core_config.settings.resolved_storage_uri.startswith("s3")
    processed_with_no_errors = True
    converted = 0
    cleared = 0

    try:
        # The raw column, not the read schema: the schema resolves the value
        # into a signed URL, which would look like a legacy path and get every
        # photo cleared.
        stored_photos = users_crud.get_stored_photo_keys(db)
    except Exception as err:
        logger.error(
            f"Migration 10 - Error fetching users: {err}", exc_info=err, extra=core_logger.context(console=True)
        )
        return

    for user_id, stored in stored_photos:
        # A key never contains a separator, so this is idempotent.
        if not stored or ("/" not in stored and "\\" not in stored):
            continue
        try:
            source = _legacy_file(stored)
            if source is None:
                logger.warning(
                    f"Migration 10 - user {user_id} has no photo at {stored}; clearing the reference",
                    extra=core_logger.context(console=True),
                )
                users_crud.set_user_photo_key(user_id, None, db)
                cleared += 1
                continue

            key = source.name
            if is_local:
                # The area already resolves to this file's directory, so
                # rewriting the row is the whole migration.
                expected = _user_image_area_dir() / key
                if source != expected:
                    os.replace(source, expected)
            else:
                storage.save(users_signing.USER_IMAGE_STORAGE_AREA, key, source.read_bytes())

            users_crud.set_user_photo_key(user_id, key, db)
            converted += 1
        except Exception as err:
            logger.error(
                f"Migration 10 - Error processing user {user_id}: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            processed_with_no_errors = False
            continue

    logger.info(
        f"Migration 10 - rewrote {converted} user photo path(s) to storage keys, cleared {cleared} missing",
        extra=core_logger.context(console=True),
    )

    if processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(10, db)
        except Exception as err:
            logger.error(
                f"Migration 10 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
    else:
        logger.warning(
            "Migration 10 - some records were not processed; migration will run again on next startup",
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 10", extra=core_logger.context(console=True))
