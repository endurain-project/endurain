"""API routes for follower relationships and follow requests."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.followers.schema as followers_schema
import modules.followers.service as followers_service
import modules.users.users.dependencies as users_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/users/{user_id}/followers",
    response_model=list[followers_schema.FollowRelationship],
    status_code=status.HTTP_200_OK,
)
def list_user_followers(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[followers_schema.FollowRelationship]:
    """List a user's followers.

    Privacy-aware: only the user themselves or an accepted follower may list them.
    """
    return followers_service.list_followers(user_id, token_user_id, db)


@router.get(
    "/users/{user_id}/followers/count",
    response_model=int,
    status_code=status.HTTP_200_OK,
)
def count_user_followers(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    accepted_only: Annotated[bool, Query()] = False,
) -> int:
    """Count a user's followers (privacy-aware).

    Pass ``accepted_only=true`` to exclude pending follow requests.
    """
    return followers_service.count_followers(user_id, token_user_id, db, accepted_only=accepted_only)


@router.get(
    "/users/{user_id}/following",
    response_model=list[followers_schema.FollowRelationship],
    status_code=status.HTTP_200_OK,
)
def list_user_following(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[followers_schema.FollowRelationship]:
    """List who a user follows.

    Privacy-aware: only the user themselves or an accepted follower may list them.
    """
    return followers_service.list_following(user_id, token_user_id, db)


@router.get(
    "/users/{user_id}/following/count",
    response_model=int,
    status_code=status.HTTP_200_OK,
)
def count_user_following(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    accepted_only: Annotated[bool, Query()] = False,
) -> int:
    """Count who a user follows (privacy-aware).

    Pass ``accepted_only=true`` to exclude pending follow requests.
    """
    return followers_service.count_following(user_id, token_user_id, db, accepted_only=accepted_only)


@router.get(
    "/users/{user_id}/relationship",
    response_model=followers_schema.RelationshipView,
    status_code=status.HTTP_200_OK,
)
def read_user_relationship(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.RelationshipView:
    """Return the authenticated user's relationship with ``user_id``, both directions.

    Reports the requester's outgoing follow of ``user_id`` and ``user_id``'s
    incoming follow of the requester; only relationships the requester is part of
    are ever exposed.
    """
    return followers_service.get_user_relationship(user_id, token_user_id, db)


@router.post(
    "/users/{user_id}/follow",
    response_model=followers_schema.FollowRelationship,
    status_code=status.HTTP_201_CREATED,
)
def follow_user(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationship:
    """Request to follow ``user_id`` as the authenticated user."""
    return followers_service.follow_user(token_user_id, user_id, db)


@router.post(
    "/users/{user_id}/follow/accept",
    response_model=followers_schema.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def accept_follow(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.MessageResponse:
    """Accept the pending follow request from ``user_id``."""
    followers_service.accept_follow_request(token_user_id, user_id, db)
    return followers_schema.MessageResponse(detail="Follower accepted successfully")


@router.delete(
    "/users/{user_id}/follow",
    response_model=followers_schema.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def unfollow_user(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.MessageResponse:
    """Unfollow ``user_id`` as the authenticated user."""
    followers_service.unfollow_user(token_user_id, user_id, db)
    return followers_schema.MessageResponse(detail="Unfollowed successfully")


@router.delete(
    "/users/{user_id}/follower",
    response_model=followers_schema.MessageResponse,
    status_code=status.HTTP_200_OK,
)
def remove_follower(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["profile"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.MessageResponse:
    """Remove ``user_id`` as a follower of the authenticated user."""
    followers_service.remove_follower(token_user_id, user_id, db)
    return followers_schema.MessageResponse(detail="Follower removed successfully")
