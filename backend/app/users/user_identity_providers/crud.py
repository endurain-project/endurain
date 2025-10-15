from datetime import datetime, timezone
from sqlalchemy import exists
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from users.user_identity_providers import models as user_idp_models


def get_idp_has_user_links(idp_id: int, db: Session) -> bool:
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


def get_user_idp_link(
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


def get_user_idp_link_by_subject(
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


def get_user_idp_links(
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


def create_user_idp_link(
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


def update_user_idp_last_login(
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
    db_link = get_user_idp_link(user_id, idp_id, db)
    if db_link:
        db_link.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_link)
    return db_link


def delete_user_idp_link(user_id: int, idp_id: int, db: Session) -> bool:
    """
    Deletes the link between a user and an identity provider (IDP) from the database.

    Args:
        user_id (int): The ID of the user whose IDP link is to be deleted.
        idp_id (int): The ID of the identity provider to unlink from the user.
        db (Session): The SQLAlchemy database session to use for the operation.

    Returns:
        bool: True if the link was found and deleted, False otherwise.
    """
    db_link = get_user_idp_link(user_id, idp_id, db)
    if db_link:
        db.delete(db_link)
        db.commit()
        return True
    return False
