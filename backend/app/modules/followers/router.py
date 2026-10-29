"""API routes for follower relationships and follow requests."""

from fastapi import APIRouter, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.followers.schema as followers_schema
import modules.followers.service as followers_service

# Define the API router
router = APIRouter()


@router.get(
    "/follow-requests",
    response_model=followers_schema.FollowRelationshipPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
)
def list_follow_requests(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
) -> followers_schema.FollowRelationshipPage:
    """List the follow requests awaiting the authenticated user's decision.

    Always scoped to the caller, so there is no user id to supply and no way to
    read anyone else's pending requests. The page also carries each requester's public profile in
    ``users`` (the projection ``GET /users/id/{user_id}`` returns), so a token with
    ``followers:read`` alone receives it too.
    """
    return followers_service.list_pending_requests(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.patch(
    "/follow-requests/{follower_id}",
    response_model=followers_schema.FollowRelationshipRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def accept_follow_request(
    request: Request,
    follower_id: core_dependencies.PositiveId,
    accept: followers_schema.FollowRequestAccept,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def reject_follow_request(
    request: Request,
    follower_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Decline the pending follow request from ``follower_id``.

    Distinct from removing an accepted follower: this refuses access that was
    never granted, which is a different decision even though the row is the same.
    Scoped to pending requests, so removing an accepted follower goes through the
    relationship route rather than arriving here by accident.
    """
    followers_service.reject_follow_request(token_user_id, follower_id, db)
