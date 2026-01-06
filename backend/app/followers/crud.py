import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import followers.models as followers_models

import core.logger as core_logger

import notifications.utils as notifications_utils

import websocket.manager as websocket_manager


def get_all_followers_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followers = (
            db.query(followers_models.Follower)
            .filter(followers_models.Follower.follower_id == user_id)
            .all()
        )

        # Check if followers is None and return None if it is
        if followers is None:
            return None

        # Return the followers
        return followers
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_followers_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_accepted_followers_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followers = (
            db.query(followers_models.Follower)
            .filter(
                (followers_models.Follower.follower_id == user_id)
                & (followers_models.Follower.is_accepted)
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
        core_logger.print_to_log(
            f"Error in get_accepted_followers_by_user_id: {err}", "error", exc=err
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
            db.query(followers_models.Follower)
            .filter(followers_models.Follower.following_id == user_id)
            .all()
        )

        # Check if followers is None and return None if it is
        if followings is None:
            return None

        # Return the followers
        return followings
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_following_by_user_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_accepted_following_by_user_id(user_id: int, db: Session):
    try:
        # Get the followers by user ID from the database
        followings = (
            db.query(followers_models.Follower)
            .filter(
                (followers_models.Follower.following_id == user_id)
                & (followers_models.Follower.is_accepted)
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
        core_logger.print_to_log(
            f"Error in get_accepted_following_by_user_id: {err}", "error", exc=err
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
            db.query(followers_models.Follower)
            .filter(
                (followers_models.Follower.follower_id == user_id)
                & (followers_models.Follower.following_id == target_user_id)
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
        core_logger.print_to_log(
            f"Error in get_follower_for_user_id_and_target_user_id: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


async def create_follower(
    user_id: int,
    target_user_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    try:
        # Create a new follow relationship
        new_follow = followers_models.Follower(
            follower_id=user_id, following_id=target_user_id, is_accepted=False
        )

        # Add the new follow relationship to the database
        db.add(new_follow)
        db.commit()

        await notifications_utils.create_new_follower_request_notification(
            user_id, target_user_id, websocket_manager, db
        )

        # Return the gear
        return new_follow
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_follower: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


async def accept_follower(
    user_id: int,
    target_user_id: int,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    try:
        # Get the follower record
        accept_follow = (
            db.query(followers_models.Follower)
            .filter(
                (followers_models.Follower.follower_id == target_user_id)
                & (followers_models.Follower.following_id == user_id)
                & (followers_models.Follower.is_accepted == False)
            )
            .first()
        )

        # check if accept_follow is None and raise an HTTPException if it is
        if accept_follow is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Follower record not found",
            )

        # Accept the follow request by changing the "is_accepted" column to True
        accept_follow.is_accepted = True

        # Commit the transaction
        db.commit()

        await notifications_utils.create_accepted_follower_request_notification(
            user_id, target_user_id, websocket_manager, db
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in accept_follower: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_follower(user_id: int, target_user_id: int, db: Session):
    try:
        # Delete the follower record
        num_deleted = (
            db.query(followers_models.Follower)
            .filter(
                (followers_models.Follower.follower_id == user_id)
                & (followers_models.Follower.following_id == target_user_id)
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
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_follower: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
