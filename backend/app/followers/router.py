import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import followers.schema as followers_schema
import followers.crud as followers_crud

import users.users.dependencies as users_dependencies

import auth.security as auth_security

import core.database as core_database

import websocket.manager as websocket_manager

# Define the API router
router = APIRouter()


@router.get(
    "/user/{user_id}/followers/all",
    response_model=list[followers_schema.Follower] | None,
)
async def get_user_follower_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return followers
    return followers_crud.get_all_following_by_user_id(user_id, db)


@router.get(
    "/user/{user_id}/followers/count/all",
    response_model=int,
)
async def get_user_follower_count_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return followers
    followers = followers_crud.get_all_followers_by_user_id(user_id, db)

    # Check if followers is None and return 0 if it is
    if followers is None:
        return 0

    # Return the number of followers
    return len(followers)


@router.get(
    "/user/{user_id}/followers/count/accepted",
    response_model=int,
)
async def get_user_follower_count(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return followers
    followers = followers_crud.get_accepted_followers_by_user_id(user_id, db)

    # Check if followers is None and return 0 if it is
    if followers is None:
        return 0

    # Return the number of followers
    return len(followers)


@router.get(
    "/user/{user_id}/following/all",
    response_model=list[followers_schema.Follower] | None,
)
async def get_user_following_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return followings
    return followers_crud.get_all_followers_by_user_id(user_id, db)


@router.get(
    "/user/{user_id}/following/count/all",
    response_model=int,
)
async def get_user_following_count_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return followings
    followings = followers_crud.get_all_following_by_user_id(user_id, db)

    # Check if followings is None and return 0 if it is
    if followings is None:
        return 0

    # Return the number of followings
    return len(followings)


@router.get(
    "/user/{user_id}/following/count/accepted",
    response_model=int,
)
async def get_user_following_count(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return followings
    followings = followers_crud.get_accepted_following_by_user_id(user_id, db)

    # Check if followings is None and return 0 if it is
    if followings is None:
        return 0

    # Return the number of followings
    return len(followings)


@router.get(
    "/user/{user_id}/targetUser/{target_user_id}",
    response_model=followers_schema.Follower | None,
)
async def read_followers_user_specific_user(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Return the follower
    return followers_crud.get_follower_for_user_id_and_target_user_id(
        user_id, target_user_id, db
    )


@router.post(
    "/create/targetUser/{target_user_id}",
    status_code=201,
    response_model=followers_schema.Follower,
)
async def create_follow(
    # user_id: int,
    # validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["profile"])
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Create the follower and return it
    return await followers_crud.create_follower(
        token_user_id, target_user_id, websocket_manager, db
    )


@router.put(
    "/accept/targetUser/{target_user_id}",
)
async def accept_follow(
    # user_id: int,
    # validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["profile"])
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Accept the follower
    await followers_crud.accept_follower(
        token_user_id, target_user_id, websocket_manager, db
    )

    # Return success message
    return {"detail": "Follower accepted successfully"}


@router.delete(
    "/delete/follower/targetUser/{target_user_id}",
)
async def delete_follower(
    # user_id: int,
    # validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["profile"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Delete the follower
    followers_crud.delete_follower(token_user_id, target_user_id, db)

    # Return success message
    return {"detail": "Follower record deleted successfully"}


@router.delete(
    "/delete/following/targetUser/{target_user_id}",
)
async def delete_following(
    # user_id: int,
    # validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["profile"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Delete the follower
    followers_crud.delete_follower(target_user_id, token_user_id, db)

    # Return success message
    return {"detail": "Follower record deleted successfully"}
