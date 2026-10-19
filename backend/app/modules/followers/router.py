"""API routes for follower relationships and follow requests."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.followers.schema as followers_schema
import modules.followers.service as followers_service

# Define the API router
router = APIRouter()


@router.get(
    "/users/{user_id}/followers",
    response_model=followers_schema.FollowRelationshipPage,
)
def list_user_followers(
    user_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    accepted_only: Annotated[bool, Query()] = False,
) -> followers_schema.FollowRelationshipPage:
    """List a user's followers, with the matching total.

    Privacy-aware: only the user themselves or an accepted follower may list them.
    """
    return followers_service.list_followers(
        user_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        accepted_only=accepted_only,
    )


@router.get(
    "/users/{user_id}/following",
    response_model=followers_schema.FollowRelationshipPage,
)
def list_user_following(
    user_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    accepted_only: Annotated[bool, Query()] = False,
) -> followers_schema.FollowRelationshipPage:
    """List who a user follows, with the matching total.

    Privacy-aware: only the user themselves or an accepted follower may list them.
    """
    return followers_service.list_following(
        user_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        accepted_only=accepted_only,
    )


@router.get(
    "/users/{user_id}/relationship",
    response_model=followers_schema.RelationshipRead,
)
def read_user_relationship(
    user_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.RelationshipRead:
    """Return the authenticated user's relationship with ``user_id``, both directions.

    Reports the requester's outgoing follow of ``user_id`` and ``user_id``'s
    incoming follow of the requester; only relationships the requester is part of
    are ever exposed.
    """
    return followers_service.get_user_relationship(user_id, token_user_id, db)


@router.get(
    "/follow-requests",
    response_model=followers_schema.FollowRelationshipPage,
)
def list_follow_requests(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
) -> followers_schema.FollowRelationshipPage:
    """List the follow requests awaiting the authenticated user's decision.

    Always scoped to the caller, so there is no user id to supply and no way to
    read anyone else's pending requests.
    """
    return followers_service.list_pending_requests(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.post(
    "/users/{user_id}/followers",
    response_model=followers_schema.FollowRelationshipRead,
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def follow_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationshipRead:
    """Add the authenticated user to ``user_id``'s followers.

    Always created pending: a follow takes effect only once the target accepts
    it, so the returned ``status`` is ``pending`` and the target is notified.
    """
    return followers_service.follow_user(token_user_id, user_id, db)


@router.patch(
    "/follow-requests/{follower_id}",
    response_model=followers_schema.FollowRelationshipRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def accept_follow_request(
    request: Request,
    follower_id: core_dependencies.PositiveId,
    accept: followers_schema.FollowRequestAccept,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> followers_schema.FollowRelationshipRead:
    """Accept the pending follow request from ``follower_id``.

    Accepting is the only transition this route writes; declining is ``DELETE``
    on the same path, because it removes the request rather than moving it to a
    rejected state. The route is named for what it does so a client does not read
    a general "decide" surface into it and send a rejection here.

    Returns the row as persisted rather than one assembled from the request, so
    the response cannot claim a state the database does not hold.
    """
    return followers_service.accept_follow_request(token_user_id, follower_id, db)


@router.delete(
    "/follow-requests/{follower_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def reject_follow_request(
    request: Request,
    follower_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """Decline the pending follow request from ``follower_id``.

    Distinct from removing an accepted follower: this refuses access that was
    never granted, which is a different decision even though the row is the same.
    Scoped to pending requests, so removing an accepted follower goes through the
    relationship route rather than arriving here by accident.
    """
    followers_service.reject_follow_request(token_user_id, follower_id, db)


@router.delete(
    "/users/{user_id}/followers/{follower_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_follow_relationship(
    request: Request,
    user_id: core_dependencies.PositiveId,
    follower_id: core_dependencies.PositiveId,
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
