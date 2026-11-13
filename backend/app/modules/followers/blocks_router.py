"""API routes for the signed-in user's block list, served under ``/profile/blocked-users``."""

from fastapi import APIRouter, Request, Security, status

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.followers.dependencies as followers_dependencies
import modules.followers.service as followers_service
import modules.users.users.schema as users_schema

router = APIRouter()


@router.get(
    "",
    response_model=users_schema.UserPublicPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:read"])],
)
def list_blocked_users(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
) -> users_schema.UserPublicPage:
    """List the users the caller has blocked, most recently blocked first.

    Each item is the user's public profile. A blocked user who is inactive or awaiting approval has no public
    profile and is neither listed nor counted.
    """
    return followers_service.list_blocked_users(
        token_user_id, db, page_number=page.page_number, num_records=page.num_records
    )


@router.put(
    "/{user_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def block_user(
    request: Request,
    user_id: followers_dependencies.OtherUserId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Block a user.

    The blocked user can no longer request to follow the caller, and every follow between the two, pending
    requests included, is removed without telling them. Blocking someone already blocked changes nothing. The
    answer is the same for any other user id, whether or not the account exists, so the route cannot be used to
    look accounts up. Blocking yourself is `422`.
    """
    followers_service.block_user(token_user_id, user_id, db)


@router.delete(
    "/{user_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["followers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def unblock_user(
    request: Request,
    user_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Unblock a user. Follows removed by the block are not restored.

    `404` when the caller has not blocked that user.
    """
    followers_service.unblock_user(token_user_id, user_id, db)
