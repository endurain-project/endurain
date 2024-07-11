import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import followers.schema as followers_schema
import followers.crud as followers_crud

import users.dependencies as users_dependencies

import session.security as session_security

import database

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/followers/user/{user_id}/followers/all",
    response_model=list[followers_schema.Follower] | None,
    tags=["followers"],
)
async def get_user_follower_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Return followers
    return followers_crud.get_all_following_by_user_id(user_id, db)


@router.get(
    "/followers/user/{user_id}/followers/count/all",
    response_model=int,
    tags=["followers"],
)
async def get_user_follower_count_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
    "/followers/user/{user_id}/followers/count/accepted",
    response_model=int,
    tags=["followers"],
)
async def get_user_follower_count(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
    "/followers/user/{user_id}/following/all",
    response_model=list[followers_schema.Follower] | None,
    tags=["followers"],
)
async def get_user_following_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Return followings
    return followers_crud.get_all_followers_by_user_id(user_id, db)


@router.get(
    "/followers/user/{user_id}/following/count/all",
    response_model=int,
    tags=["followers"],
)
async def get_user_following_count_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
    "/followers/user/{user_id}/following/count/accepted",
    response_model=int,
    tags=["followers"],
)
async def get_user_following_count(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
    "/followers/user/{user_id}/targetUser/{target_user_id}",
    response_model=followers_schema.Follower | None,
    tags=["followers"],
)
async def read_followers_user_specific_user(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Return the follower
    return followers_crud.get_follower_for_user_id_and_target_user_id(
        user_id, target_user_id, db
    )


@router.post(
    "/followers/create/user/{user_id}/targetUser/{target_user_id}",
    status_code=201,
    tags=["followers"],
)
async def create_follow(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Create the follower
    #new_follow = followers_crud.create_follower(user_id, target_user_id, db)

    # Return the ID of the gear created
    return {"detail": "Follower record created successfully"}


@router.put("/followers/accept/user/{user_id}/targetUser/{target_user_id}",
    tags=["followers"],
)
async def accept_follow(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Accept the follower
    followers_crud.accept_follower(user_id, target_user_id, db)

    # Return success message
    return {"detail": "Follower record accepted successfully"}


@router.delete(
    "/followers/delete/user/{user_id}/targetUser/{target_user_id}",
    tags=["followers"],
)
async def delete_follow(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_target_user_id)
    ],
    validate_token: Annotated[Callable, Depends(session_security.validate_token_expiration)],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Delete the follower
    followers_crud.delete_follower(user_id, target_user_id, db)

    # Return success message
    return {"detail": "Follower record deleted successfully"}
