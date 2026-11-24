"""The signed-in user's profile photo: the flows ``/profile/photo`` runs."""

import uuid
from collections.abc import Callable

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema


def set_photo(
    user_id: uuid.UUID,
    filename: str | None,
    read_data: Callable[[], bytes],
    storage: platform_providers.StorageProvider,
    db: Session,
) -> tuple[users_schema.UserPhotoRead, bool]:
    """Validate and store the user's photo and read back where it is served.

    Args:
        user_id: The user whose photo is being set.
        filename: The uploaded file's name.
        read_data: Reads and validates the uploaded image once the user and the extension are accepted.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The servable URL of the new photo, and whether it replaced an earlier one.

    Raises:
        NotFoundError: If the user does not exist.
        InvalidInputError: If the upload has no filename.
        UnsupportedMediaTypeError: If the extension is not an allowed image type.
    """
    replaced = users_integration.upload_user_photo(user_id, filename, read_data, storage, db)
    photo = users_schema.UserPhotoRead(photo_path=users_integration.require_user(user_id, db).photo_path)
    return photo, replaced


def delete_photo(user_id: uuid.UUID, storage: platform_providers.StorageProvider, db: Session) -> None:
    """Clear the user's photo reference and delete the stored blobs.

    Args:
        user_id: The user whose photo to delete.
        storage: The platform storage provider.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    users_integration.delete_user_photo(user_id, storage, db)
