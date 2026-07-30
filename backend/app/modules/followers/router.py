"""API routes for follower relationships and follow requests."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.followers.schema as followers_schema
import modules.followers.service as followers_service
import modules.users.users.dependencies as users_dependencies

# Default page size when a list request omits pagination.
_DEFAULT_NUM_RECORDS = core_pagination.DEFAULT_NUM_RECORDS
# Hard cap on the client-requested page size, bounding query and serialization
# cost per request (defense against resource exhaustion). Shared with the
# activities router so the two template modules cannot drift.
_MAX_NUM_RECORDS = core_pagination.MAX_NUM_RECORDS

# Define the API router
router = APIRouter()


@router.get(
    "/users/{user_id}/followers",
    response_model=followers_schema.FollowRelationshipPage,
    status_code=status.HTTP_200_OK,
)
def list_user_followers(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
    accepted_only: Annotated[bool, Query()] = False,
) -> followers_schema.FollowRelationshipPage:
    """List a user's followers, with the matching total.

    Privacy-aware: only the user themselves or an accepted follower may list them.
    """
    return followers_service.list_followers(
        user_id,
        token_user_id,
        db,
        page_number=page_number or 1,
        num_records=num_records or _DEFAULT_NUM_RECORDS,
        accepted_only=accepted_only,
    )


@router.get(
    "/users/{user_id}/following",
    response_model=followers_schema.FollowRelationshipPage,
    status_code=status.HTTP_200_OK,
)
def list_user_following(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
    accepted_only: Annotated[bool, Query()] = False,
) -> followers_schema.FollowRelationshipPage:
    """List who a user follows, with the matching total.

    Privacy-aware: only the user themselves or an accepted follower may list them.
    """
    return followers_service.list_following(
        user_id,
        token_user_id,
        db,
        page_number=page_number or 1,
        num_records=num_records or _DEFAULT_NUM_RECORDS,
        accepted_only=accepted_only,
    )


@router.get(
    "/users/{user_id}/relationship",
    response_model=followers_schema.RelationshipView,
    status_code=status.HTTP_200_OK,
)
def read_user_relationship(
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.RelationshipView:
    """Return the authenticated user's relationship with ``user_id``, both directions.

    Reports the requester's outgoing follow of ``user_id`` and ``user_id``'s
    incoming follow of the requester; only relationships the requester is part of
    are ever exposed.
    """
    return followers_service.get_user_relationship(user_id, token_user_id, db)


@router.get(
    "/follow-requests",
    response_model=followers_schema.FollowRelationshipPage,
    status_code=status.HTTP_200_OK,
)
def list_follow_requests(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
) -> followers_schema.FollowRelationshipPage:
    """List the follow requests awaiting the authenticated user's decision.

    Always scoped to the caller, so there is no user id to supply and no way to
    read anyone else's pending requests.
    """
    return followers_service.list_pending_requests(
        token_user_id,
        db,
        page_number=page_number or 1,
        num_records=num_records or _DEFAULT_NUM_RECORDS,
    )


@router.post(
    "/users/{user_id}/followers",
    response_model=followers_schema.FollowRelationship,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def follow_user(
    request: Request,
    user_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationship:
    """Add the authenticated user to ``user_id``'s followers.

    Creates the relationship pending or accepted according to the target's
    privacy settings; the returned ``status`` says which.
    """
    return followers_service.follow_user(token_user_id, user_id, db)


@router.patch(
    "/follow-requests/{requester_user_id}",
    response_model=followers_schema.FollowRelationship,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def decide_follow_request(
    request: Request,
    requester_user_id: int,
    decision: followers_schema.FollowRequestDecision,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationship:
    """Accept the pending follow request from ``requester_user_id``.

    Returns the row as persisted rather than one assembled from the request, so
    the response cannot claim a state the database does not hold.
    """
    return followers_service.accept_follow_request(token_user_id, requester_user_id, db)


@router.delete(
    "/follow-requests/{requester_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def reject_follow_request(
    request: Request,
    requester_user_id: int,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """Decline the pending follow request from ``requester_user_id``.

    Distinct from removing an accepted follower: this refuses access that was
    never granted, which is a different decision even though the row is the same.
    """
    followers_service.reject_follow_request(token_user_id, requester_user_id, db)


@router.delete(
    "/users/{user_id}/followers/{follower_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_follow_relationship(
    request: Request,
    user_id: int,
    follower_id: int,
    _validate_user_id: Annotated[None, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """Delete the follow relationship where ``follower_id`` follows ``user_id``.

    Serves both directions. Unfollowing is ``follower_id`` = the caller; removing
    a follower is ``user_id`` = the caller. Either party may delete it, and the
    caller must be one of them.
    """
    followers_service.delete_relationship(user_id, follower_id, token_user_id, db)
