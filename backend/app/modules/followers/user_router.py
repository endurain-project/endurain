"""API routes for a user's follower relationships, served under ``/users/{user_id}``."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.followers.schema as followers_schema
import modules.followers.service as followers_service

router = APIRouter()


@router.get(
    "/{user_id}/followers",
    response_model=followers_schema.FollowRelationshipPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
)
def list_user_followers(
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    accepted_only: Annotated[bool, Query()] = False,
) -> followers_schema.FollowRelationshipPage:
    """List a user's followers, with the matching total.

    Privacy-aware: only the user themselves or an accepted follower may list them. The page also
    carries each follower's public profile in ``users`` (the projection ``GET /users/id/{user_id}``
    returns), so a token with ``followers:read`` alone receives it too.
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
    "/{user_id}/following",
    response_model=followers_schema.FollowRelationshipPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
)
def list_user_following(
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    accepted_only: Annotated[bool, Query()] = False,
) -> followers_schema.FollowRelationshipPage:
    """List who a user follows, with the matching total.

    Privacy-aware: only the user themselves or an accepted follower may list them. The page also
    carries each followee's public profile in ``users`` (the projection ``GET /users/id/{user_id}``
    returns), so a token with ``followers:read`` alone receives it too.
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
    "/{user_id}/relationship",
    response_model=followers_schema.RelationshipRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
)
def read_user_relationship(
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> followers_schema.RelationshipRead:
    """Return the authenticated user's relationship with ``user_id``, both directions.

    Reports the requester's outgoing follow of ``user_id`` and ``user_id``'s
    incoming follow of the requester; only relationships the requester is part of
    are ever exposed.
    """
    return followers_service.get_user_relationship(user_id, token_user_id, db)


@router.post(
    "/{user_id}/followers",
    response_model=followers_schema.FollowRelationshipRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def follow_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> followers_schema.FollowRelationshipRead:
    """Add the authenticated user to ``user_id``'s followers.

    Always created pending: a follow takes effect only once the target accepts
    it, so the returned ``status`` is ``pending`` and the target is notified.
    """
    return followers_service.follow_user(token_user_id, user_id, db)


@router.delete(
    "/{user_id}/followers/{follower_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_follow_relationship(
    request: Request,
    user_id: core_dependencies.PositiveId,
    follower_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete the follow relationship where ``follower_id`` follows ``user_id``.

    Serves both directions. Unfollowing is ``follower_id`` = the caller; removing
    a follower is ``user_id`` = the caller. Either party may delete it, and the
    caller must be one of them.
    """
    followers_service.delete_relationship(user_id, follower_id, token_user_id, db)
