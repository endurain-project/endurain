import logging

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import unquote

import models
from schemas import schema_gear

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_all_followers_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followers = (
            db.query(models.Follower)
            .filter(models.Follower.follower_id == user_id)
            .all()
        )

        # Check if followers is None and return None if it is
        if followers is None:
            return None

        # Return the followers
        return followers
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_all_followers_by_user_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_accepted_followers_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followers = (
            db.query(models.Follower)
            .filter(
                (models.Follower.follower_id == user_id)
                & (models.Follower.is_accepted == True)
            )
            .all()
        )

        # Check if followers is None and return None if it is
        if followers is None:
            return None

        # Return the followers
        return followers
    except Exception as err:
        # Log the exception
        logger.error(
            f"Error in get_accepted_followers_by_user_id: {err}", exc_info=True
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_following_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followings = (
            db.query(models.Follower)
            .filter(models.Follower.following_id == user_id)
            .all()
        )

        # Check if followers is None and return None if it is
        if followings is None:
            return None

        # Return the followers
        return followings
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_all_following_by_user_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_accepted_following_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followings = (
            db.query(models.Follower)
            .filter(
                (models.Follower.following_id == user_id)
                & (models.Follower.is_accepted == True)
            )
            .all()
        )

        # Check if followers is None and return None if it is
        if followings is None:
            return None

        # Return the followers
        return followings
    except Exception as err:
        # Log the exception
        logger.error(
            f"Error in get_accepted_following_by_user_id: {err}", exc_info=True
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_follower_for_user_id_and_target_user_id(
    user_id: int, target_user_id: int, db: Session
):
    try:
        # Get the follower by user ID and target user ID from the database
        follower = (
            db.query(models.Follower)
            .filter(
                (models.Follower.follower_id == user_id)
                & (models.Follower.following_id == target_user_id)
            )
            .first()
        )

        # Check if follower is None and return None if it is
        if follower is None:
            return None

        # Return the follower
        return follower
    except Exception as err:
        # Log the exception
        logger.error(
            f"Error in get_follower_for_user_id_and_target_user_id: {err}",
            exc_info=True,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_follower(user_id: int, target_user_id: int, db: Session):
    try:
        # Create a new follow relationship
        new_follow = models.Follower(
            follower_id=user_id, following_id=target_user_id, is_accepted=False
        )

        # Add the new follow relationship to the database
        db.add(new_follow)
        db.commit()

        # Return the gear
        return new_follow
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(
            f"Error in create_follower: {err}",
            exc_info=True,
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_follower(user_id: int, target_user_id: int, db: Session):
    try:
        num_deleted = (
            db.query(models.Follower)
            .filter(
                (models.Follower.follower_id == user_id)
                & (models.Follower.following_id == target_user_id)
            )
            .delete()
        )

        # Check if the user was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Follower record not found",
            )

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(
            f"Error in get_follower_for_user_id_and_target_user_id: {err}",
            exc_info=True,
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
