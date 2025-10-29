from datetime import datetime, timezone
from sqlalchemy import exists
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from users.user_identity_providers import models as user_idp_models


def check_user_identity_providers_by_idp_id(idp_id: int, db: Session) -> bool:
    """
    Checks if there are any user links associated with a given identity provider ID.

    Args:
        idp_id (int): The ID of the identity provider to check for user links.
        db (Session): The SQLAlchemy database session to use for the query.

    Returns:
        bool: True if there is at least one user linked to the specified identity provider, False otherwise.
    """
    return db.query(
        exists().where(user_idp_models.UserIdentityProvider.idp_id == idp_id)
    ).scalar()


def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int, idp_id: int, db: Session
) -> user_idp_models.UserIdentityProvider | None:
    """
    Retrieve the UserIdentityProvider link for a specific user and identity provider.

    Args:
        user_id (int): The ID of the user.
        idp_id (int): The ID of the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        UserIdentityProvider | None: The UserIdentityProvider instance if found, otherwise None.
    """
    return (
        db.query(user_idp_models.UserIdentityProvider)
        .filter(
            user_idp_models.UserIdentityProvider.user_id == user_id,
            user_idp_models.UserIdentityProvider.idp_id == idp_id,
        )
        .first()
    )


def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int, idp_subject: str, db: Session
) -> user_idp_models.UserIdentityProvider | None:
    """
    Retrieve a UserIdentityProvider record by identity provider ID and subject.

    Args:
        idp_id (int): The ID of the identity provider.
        idp_subject (str): The subject identifier from the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        UserIdentityProvider | None: The matching UserIdentityProvider record if found, otherwise None.
    """
    return (
        db.query(user_idp_models.UserIdentityProvider)
        .filter(
            user_idp_models.UserIdentityProvider.idp_id == idp_id,
            user_idp_models.UserIdentityProvider.idp_subject == idp_subject,
        )
        .first()
    )


def get_user_identity_providers_by_user_id(
    user_id: int, db: Session
) -> list[user_idp_models.UserIdentityProvider]:
    """
    Retrieve all identity provider links associated with a given user.

    Args:
        user_id (int): The ID of the user whose identity provider links are to be retrieved.
        db (Session): The SQLAlchemy database session to use for the query.

    Returns:
        list[user_idp_models.UserIdentityProvider]: A list of UserIdentityProvider objects linked to the specified user.
    """
    return (
        db.query(user_idp_models.UserIdentityProvider)
        .filter(user_idp_models.UserIdentityProvider.user_id == user_id)
        .all()
    )


def get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int, idp_id: int, db: Session
) -> str | None:
    """
    Get the encrypted refresh token for a user-IdP link.

    This function retrieves the encrypted refresh token. The caller is responsible
    for decrypting it using Fernet before use.

    Args:
        user_id (int): The ID of the user.
        idp_id (int): The ID of the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        str | None: The encrypted refresh token string if found, otherwise None.

    Security Note:
        - Returns the encrypted token (not plaintext)
        - Caller must decrypt using Fernet
        - Returns None if link doesn't exist or token is not set
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
    if db_link:
        return db_link.idp_refresh_token
    return None


def create_user_identity_provider(
    user_id: int, idp_id: int, idp_subject: str, db: Session
) -> user_idp_models.UserIdentityProvider:
    """
    Creates a link between a user and an identity provider (IDP) in the database.

    Args:
        user_id (int): The ID of the user to link.
        idp_id (int): The ID of the identity provider.
        idp_subject (str): The subject identifier from the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        user_idp_models.UserIdentityProvider: The newly created UserIdentityProvider link object.
    """
    db_link = user_idp_models.UserIdentityProvider(
        user_id=user_id, idp_id=idp_id, idp_subject=idp_subject, last_login=func.now()
    )
    db.add(db_link)
    db.commit()
    db.refresh(db_link)
    return db_link


def update_user_identity_provider_last_login(
    user_id: int, idp_id: int, db: Session
) -> user_idp_models.UserIdentityProvider | None:
    """
    Updates the 'last_login' timestamp for a user's identity provider link to the current UTC time.

    Args:
        user_id (int): The ID of the user.
        idp_id (int): The ID of the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        user_idp_models.UserIdentityProvider | None: The updated UserIdentityProvider link if found, otherwise None.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
    if db_link:
        db_link.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_link)
    return db_link


def store_user_identity_provider_tokens(
    user_id: int,
    idp_id: int,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
) -> user_idp_models.UserIdentityProvider | None:
    """
    Store IdP tokens for a user-IdP link.

    This function stores the encrypted refresh token and its metadata. The refresh token
    must already be encrypted using Fernet before calling this function.

    Args:
        user_id (int): The ID of the user.
        idp_id (int): The ID of the identity provider.
        encrypted_refresh_token (str): The Fernet-encrypted refresh token from the IdP.
        access_token_expires_at (datetime): When the IdP access token expires.
        db (Session): The SQLAlchemy database session.

    Returns:
        user_idp_models.UserIdentityProvider | None: The updated UserIdentityProvider link if found, otherwise None.

    Security Note:
        The refresh_token parameter must be pre-encrypted with Fernet before calling this function.
        Never pass plaintext tokens to this function.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
    if db_link:
        db_link.idp_refresh_token = encrypted_refresh_token
        db_link.idp_access_token_expires_at = access_token_expires_at
        db_link.idp_refresh_token_updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_link)
    return db_link


def clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int, idp_id: int, db: Session
) -> bool:
    """
    Clear the IdP refresh token and related metadata.

    This function should be called when:
    - User logs out
    - Token refresh fails (invalid/revoked token)
    - User unlinks the IdP
    - Security requires token invalidation

    Args:
        user_id (int): The ID of the user.
        idp_id (int): The ID of the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        bool: True if the token was cleared, False if the link was not found.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
    if db_link:
        db_link.idp_refresh_token = None
        db_link.idp_access_token_expires_at = None
        db_link.idp_refresh_token_updated_at = None
        db.commit()
        return True
    return False


def delete_user_identity_provider(user_id: int, idp_id: int, db: Session) -> bool:
    """
    Deletes the link between a user and an identity provider (IDP) from the database.

    This function implements defense-in-depth by clearing sensitive token data before
    deleting the record, even though the database CASCADE would handle deletion.

    Args:
        user_id (int): The ID of the user whose IDP link is to be deleted.
        idp_id (int): The ID of the identity provider to unlink from the user.
        db (Session): The SQLAlchemy database session to use for the operation.

    Returns:
        bool: True if the link was found and deleted, False otherwise.

    Security Note:
        Sensitive token data is explicitly cleared before deletion as a defense-in-depth measure.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)
    if db_link:
        # Clear sensitive data first (defense in depth)
        db_link.idp_refresh_token = None
        db_link.idp_access_token_expires_at = None
        db_link.idp_refresh_token_updated_at = None
        db.commit()

        # Then delete the link
        db.delete(db_link)
        db.commit()
        return True
    return False
