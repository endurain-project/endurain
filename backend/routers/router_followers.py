import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import schema_followers
from crud import crud_followers
from dependencies import (
    dependencies_database,
    dependencies_session,
    dependencies_users,
)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/followers/user/{user_id}/followers/all",
    response_model=list[schema_followers.Follower] | None,
    tags=["followers"],
)
async def get_user_follower_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return followers
    return crud_followers.get_all_following_by_user_id(user_id, db)


@router.get(
    "/followers/user/{user_id}/followers/count/all",
    response_model=int,
    tags=["followers"],
)
async def get_user_follower_count_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return followers
    followers = crud_followers.get_all_followers_by_user_id(user_id, db)

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
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return followers
    followers = crud_followers.get_accepted_followers_by_user_id(user_id, db)

    # Check if followers is None and return 0 if it is
    if followers is None:
        return 0

    # Return the number of followers
    return len(followers)


@router.get(
    "/followers/user/{user_id}/following/all",
    response_model=list[schema_followers.Follower] | None,
    tags=["followers"],
)
async def get_user_following_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return followings
    return crud_followers.get_all_followers_by_user_id(user_id, db)


@router.get(
    "/followers/user/{user_id}/following/count/all",
    response_model=int,
    tags=["followers"],
)
async def get_user_following_count_all(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return followings
    followings = crud_followers.get_all_following_by_user_id(user_id, db)

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
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return followings
    followings = crud_followers.get_accepted_following_by_user_id(user_id, db)

    # Check if followings is None and return 0 if it is
    if followings is None:
        return 0

    # Return the number of followings
    return len(followings)


@router.get(
    "/followers/user/{user_id}/targetUser/{target_user_id}",
    response_model=schema_followers.Follower | None,
    tags=["followers"],
)
async def read_followers_user_specific_user(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(dependencies_users.validate_target_user_id)
    ],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return the follower
    return crud_followers.get_follower_for_user_id_and_target_user_id(
        user_id, target_user_id, db
    )


@router.post(
    "/followers/create/user/{user_id}/targetUser/{target_user_id}",
    status_code=201,
    tags=["followers"],
)
async def create_follow(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(dependencies_users.validate_target_user_id)
    ],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Create the follower
    new_follow = crud_followers.create_follower(user_id, target_user_id, db)

    # Return the ID of the gear created
    return {"detail": "Follower record created successfully"}


@router.delete(
    "/followers/delete/user/{user_id}/targetUser/{target_user_id}",
    tags=["followers"],
)
async def delete_follow(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    target_user_id: int,
    validate_target_user_id: Annotated[
        Callable, Depends(dependencies_users.validate_target_user_id)
    ],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Delete the follower
    crud_followers.delete_follower(user_id, target_user_id, db)

    # Return success message
    return {"detail": "Follower record deleted successfully"}
