from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from . import sessionController
from jose import JWTError
from fastapi.responses import JSONResponse
from db.db import (
    Follower,
)
from dependencies import get_db_session
from sqlalchemy.orm import Session

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Define an HTTP GET route to retrieve the number of users
@router.get("/followers/user/{user_id}/targetUser/{target_user_id}")
async def read_followers_user_specific_user(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query the specific follower record
        follower = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == user_id)
                & (Follower.following_id == target_user_id)
            )
            .first()
        )

        if follower:
            # User follows target_user_id or vice versa
            response_data = {
                "follower_id": user_id,
                "following_id": target_user_id,
                "is_accepted": follower.is_accepted,
            }
            return JSONResponse(content=response_data, status_code=200)

        # Users are not following each other
        return JSONResponse(
            content={"detail": "Users are not following each other."}, status_code=404
        )

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/followers/user/{user_id}/followers/count/all")
async def get_user_follower_count_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        follower_count = (
            db_session.query(Follower).filter(Follower.follower_id == user_id).count()
        )

        # Respond with the count
        return {"follower_count": follower_count}

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/followers/user/{user_id}/followers/count")
async def get_user_follower_count(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the count of entries where user_id is equal to Follower.follower_id
        follower_count = (
            db_session.query(Follower)
            .filter((Follower.follower_id == user_id) & (Follower.is_accepted == True))
            .count()
        )

        # Respond with the count
        return {"follower_count": follower_count}

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/followers/user/{user_id}/followers/all")
async def get_user_follower_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the entries where both conditions are met
        followers = (
            db_session.query(Follower).filter(Follower.following_id == user_id).all()
        )

        # Convert the query result to a list of dictionaries
        followers_list = [
            {"follower_id": follower.follower_id, "is_accepted": follower.is_accepted}
            for follower in followers
        ]

        # Respond with the list of followers
        return {"followers": followers_list}

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/followers/user/{user_id}/following/count/all")
async def get_user_following_count_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        following_count = (
            db_session.query(Follower).filter(Follower.following_id == user_id).count()
        )

        # Respond with the count
        return {"following_count": following_count}

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/followers/user/{user_id}/following/count")
async def get_user_following_count(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the count of entries where user_id is equal to Follower.follower_id
        following_count = (
            db_session.query(Follower)
            .filter((Follower.following_id == user_id) & (Follower.is_accepted == True))
            .count()
        )

        # Respond with the count
        return {"following_count": following_count}

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/followers/user/{user_id}/following/all")
async def get_user_following_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the entries where both conditions are met
        followings = (
            db_session.query(Follower).filter(Follower.follower_id == user_id).all()
        )

        # Convert the query result to a list of dictionaries
        following_list = [
            {
                "following_id": following.following_id,
                "is_accepted": following.is_accepted,
            }
            for following in followings
        ]

        # Respond with the list of following
        return {"followings": following_list}

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.put("/followers/accept/user/{user_id}/targetUser/{target_user_id}")
async def accept_follow(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Check if the follow relationship exists and is not accepted yet
        follow_request = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == target_user_id)
                & (Follower.following_id == user_id)
                & (Follower.is_accepted == False)
            )
            .first()
        )

        if follow_request:
            # Accept the follow request by changing the "is_accepted" column to True
            follow_request.is_accepted = True
            db_session.commit()

            # Return success response
            response_data = {
                "follower_id": target_user_id,
                "following_id": user_id,
                "is_accepted": True,
            }
            return JSONResponse(content=response_data, status_code=200)
        else:
            # Follow request does not exist or has already been accepted
            raise HTTPException(status_code=400, detail="Invalid follow request.")

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/followers/create/user/{user_id}/targetUser/{target_user_id}")
async def create_follow(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Check if the follow relationship already exists
        existing_follow = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == user_id)
                & (Follower.following_id == target_user_id)
            )
            .first()
        )

        if existing_follow:
            # Follow relationship already exists
            raise HTTPException(
                status_code=400, detail="Follow relationship already exists."
            )

        # Create a new follow relationship
        new_follow = Follower(
            follower_id=user_id, following_id=target_user_id, is_accepted=False
        )

        # Add the new follow relationship to the database
        db_session.add(new_follow)
        db_session.commit()

        # Return success response
        response_data = {
            "follower_id": user_id,
            "following_id": target_user_id,
            "is_accepted": False,
        }
        return JSONResponse(content=response_data, status_code=201)

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.delete("/followers/delete/user/{user_id}/targetUser/{target_user_id}")
async def delete_follow(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query and delete the specific follower record
        follower = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == user_id)
                & (Follower.following_id == target_user_id)
            )
            .first()
        )

        if follower:
            # Delete the follower record
            db_session.delete(follower)
            db_session.commit()

            # Respond with a success message
            return JSONResponse(
                content={"detail": "Follower record deleted successfully."},
                status_code=200,
            )

        # Follower record not found
        raise HTTPException(status_code=404, detail="Follower record not found.")

    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")
