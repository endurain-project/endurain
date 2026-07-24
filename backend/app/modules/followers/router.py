"""API routes for follower relationships and follow requests."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.followers.schema as followers_schema
import modules.followers.service as followers_service
import modules.users.users.dependencies as users_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/user/{user_id}/followers/all",
    response_model=list[followers_schema.FollowRelationship],
    status_code=status.HTTP_200_OK,
)
def get_user_follower_all(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[followers_schema.FollowRelationship]:
    """Return every follower record where the user is being followed.

    Enforces the target's profile privacy: only the user themselves or an accepted
    follower may list the followers.
    """
    return followers_service.list_followers(user_id, token_user_id, db)


@router.get(
    "/user/{user_id}/followers/count/all",
    response_model=int,
    status_code=status.HTTP_200_OK,
)
def get_user_follower_count_all(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> int:
    """Return the total number of followers for a user."""
    return followers_service.count_followers(user_id, token_user_id, db)


@router.get(
    "/user/{user_id}/followers/count/accepted",
    response_model=int,
    status_code=status.HTTP_200_OK,
)
def get_user_follower_count(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> int:
    """Return the number of accepted followers for a user."""
    return followers_service.count_followers(user_id, token_user_id, db, accepted_only=True)


@router.get(
    "/user/{user_id}/following/all",
    response_model=list[followers_schema.FollowRelationship],
    status_code=status.HTTP_200_OK,
)
def get_user_following_all(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[followers_schema.FollowRelationship]:
    """Return every follow record where the user is the follower.

    Enforces the target's profile privacy: only the user themselves or an accepted
    follower may list the following set.
    """
    return followers_service.list_following(user_id, token_user_id, db)


@router.get(
    "/user/{user_id}/following/count/all",
    response_model=int,
    status_code=status.HTTP_200_OK,
)
def get_user_following_count_all(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> int:
    """Return the total number of users a given user is following."""
    return followers_service.count_following(user_id, token_user_id, db)


@router.get(
    "/user/{user_id}/following/count/accepted",
    response_model=int,
    status_code=status.HTTP_200_OK,
)
def get_user_following_count(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> int:
    """Return the number of accepted follow relationships for a user."""
    return followers_service.count_following(user_id, token_user_id, db, accepted_only=True)


@router.get(
    "/user/{user_id}/targetUser/{target_user_id}",
    response_model=followers_schema.FollowRelationship | None,
    status_code=status.HTTP_200_OK,
)
def read_followers_user_specific_user(
    user_id: int,
    target_user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _validate_target_user_id: Annotated[None, Depends(users_dependencies.validate_target_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationship | None:
    """Return the follow relationship between two specific users, if any.

    Only a participant in the relationship (the requester must be one of the two
    users) may query it, preventing arbitrary probing of who follows whom.
    """
    return followers_service.get_relationship(user_id, target_user_id, token_user_id, db)


@router.post(
    "/create/targetUser/{target_user_id}",
    response_model=followers_schema.FollowRelationship,
    status_code=status.HTTP_201_CREATED,
)
def create_follow(
    target_user_id: int,
    _validate_target_user_id: Annotated[None, Depends(users_dependencies.validate_target_user_id)],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationship:
    """Create a new follow request from the authenticated user."""
    return followers_service.follow_user(token_user_id, target_user_id, db)


@router.put(
    "/accept/targetUser/{target_user_id}",
    response_model=followers_schema.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def accept_follow(
    target_user_id: int,
    _validate_target_user_id: Annotated[None, Depends(users_dependencies.validate_target_user_id)],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.MessageResponse:
    """Accept a pending follow request from the target user."""
    followers_service.accept_follow_request(token_user_id, target_user_id, db)
    return followers_schema.MessageResponse(detail="Follower accepted successfully")


@router.delete(
    "/delete/follower/targetUser/{target_user_id}",
    response_model=followers_schema.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def delete_follower(
    target_user_id: int,
    _validate_target_user_id: Annotated[None, Depends(users_dependencies.validate_target_user_id)],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.MessageResponse:
    """Remove a user the authenticated user is following."""
    followers_service.unfollow_user(token_user_id, target_user_id, db)
    return followers_schema.MessageResponse(detail="Follower record deleted successfully")


@router.delete(
    "/delete/following/targetUser/{target_user_id}",
    response_model=followers_schema.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def delete_following(
    target_user_id: int,
    _validate_target_user_id: Annotated[None, Depends(users_dependencies.validate_target_user_id)],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.MessageResponse:
    """Remove a follower of the authenticated user."""
    followers_service.remove_follower(token_user_id, target_user_id, db)
    return followers_schema.MessageResponse(detail="Follower record deleted successfully")
