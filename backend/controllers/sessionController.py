import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from db.db import (
    User,
    AccessToken,
)  # Import your SQLAlchemy session management from db.db and models
from controllers.userController import UserResponse
from pydantic import BaseModel
from dependencies import get_db_session

router = APIRouter()

logger = logging.getLogger("myLogger")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_user_id_from_token(token: str):
    try:
        payload = jwt.decode(
            token,
            os.environ.get("SECRET_KEY"),
            algorithms=[os.environ.get("ALGORITHM")],
        )
        return payload.get("id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_exp_from_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(
            token,
            os.environ.get("SECRET_KEY"),
            algorithms=[os.environ.get("ALGORITHM")],
        )
        return payload.get("exp")
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
def get_access_type_from_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(
            token,
            os.environ.get("SECRET_KEY"),
            algorithms=[os.environ.get("ALGORITHM")],
        )
        return payload.get("access_type")
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


async def authenticate_user(
    username: str,
    password: str,
    neverExpires: bool,
    db_session: Session,
):
    try:
        # Use SQLAlchemy ORM to query the database
        user = (
            db_session.query(User)
            .filter(User.username == username, User.password == password)
            .first()
        )
        if not user:
            raise HTTPException(
                status_code=400, detail="Incorrect username or password"
            )

        # Check if there is an existing access token for the user
        access_token = (
            db_session.query(AccessToken).filter(AccessToken.user_id == user.id).first()
        )
        if access_token:
            return access_token.token

        # If there is no existing access token, create a new one
        access_token_expires = timedelta(
            minutes=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
        )
        access_token = await create_access_token(
            data={"id": user.id, "access_type": user.access_type},
            never_expire=neverExpires,
            db_session=db_session,
            expires_delta=access_token_expires,
        )

        return access_token

    except Exception as e:
        logger.error(e)
        return False


async def create_access_token(
    data: dict,
    never_expire: bool,
    db_session: Session,
    expires_delta: timedelta = None,
):
    to_encode = data.copy()
    if never_expire:
        expire = datetime.utcnow() + timedelta(days=90)
    elif expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, os.environ.get("SECRET_KEY"), algorithm=os.environ.get("ALGORITHM")
    )

    # Insert the access token into the database using SQLAlchemy
    access_token = AccessToken(
        token=encoded_jwt,
        user_id=data["id"],
        created_at=datetime.utcnow(),
        expires_at=expire,
    )

    db_session.add(access_token)
    db_session.commit()

    return encoded_jwt


def remove_expired_tokens(db_session: Session):
    try:
        # Calculate the expiration time
        expiration_time = datetime.utcnow() - timedelta(
            minutes=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
        )

        # Delete expired access tokens using SQLAlchemy ORM
        rows_deleted = (
            db_session.query(AccessToken)
            .filter(AccessToken.created_at < expiration_time)
            .delete()
        )
        db_session.commit()

        logger.info(f"{rows_deleted} access tokens deleted from the database")
    except Exception as err:
        logger.error(f"Error in remove_expired_tokens: {err}", exc_info=True)


def get_user_data(db_session: Session, token: str = Depends(oauth2_scheme)):
    try:
        validate_token(db_session=db_session, token=token)

        user_id = get_user_id_from_token(token)
        if user_id is None:
            raise HTTPException(
                status_code=401, detail="Invalid authentication credentials"
            )

        # Retrieve the user details from the database using the user ID
        user = db_session.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.strava_token is None:
            is_strava_linked = 0
        else:
            is_strava_linked = 1

        # Map the user object to a dictionary that matches the UserResponse model
        user_data = {
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "city": user.city,
            "birthdate": user.birthdate,
            "preferred_language": user.preferred_language,
            "gender": user.gender,
            "access_type": user.access_type,
            "photo_path": user.photo_path,
            "photo_path_aux": user.photo_path_aux,
            "is_active": user.is_active,
            "is_strava_linked": is_strava_linked,
        }

        return user_data
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


def validate_token(db_session: Session, token: str):
    try:
        user_id = get_user_id_from_token(token)

        exp = get_exp_from_token(token)

        access_token = (
            db_session.query(AccessToken)
            .filter(AccessToken.user_id == user_id, AccessToken.token == token)
            .first()
        )

        if access_token:
            expiration_datetime = datetime.fromtimestamp(exp)
            current_time = datetime.utcnow()
            if current_time > expiration_datetime:
                raise JWTError("Token expired")
            else:
                return {"message": "Token is valid"}
        else:
            raise JWTError("Token expired")

        # if 'exp' not in decoded_token:
        #    return {"message": "Token is valid"}
        # else:
    except JWTError:
        raise JWTError("Invalid token")


def validate_admin_access(token: str):
    try:
        user_access_type = get_access_type_from_token(token)
        if user_access_type != 2:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise JWTError("Invalid token")


class CreateTokenRequest(BaseModel):
    username: str
    password: str
    neverExpires: bool


@router.post("/token")
async def login_for_access_token(
    token: CreateTokenRequest, db_session: Session = Depends(get_db_session)
):
    access_token = await authenticate_user(
        token.username, token.password, token.neverExpires, db_session
    )
    if not access_token:
        raise HTTPException(status_code=400, detail="Unable to retrieve access token")
    return {"access_token": access_token, "token_type": "bearer"}


@router.delete("/logout/{user_id}")
async def logout(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    try:
        access_token = (
            db_session.query(AccessToken)
            .filter(AccessToken.user_id == user_id, AccessToken.token == token)
            .first()
        )
        if access_token:
            db_session.delete(access_token)
            db_session.commit()
            return {"message": "Logged out successfully"}
        else:
            raise HTTPException(status_code=404, detail="Token not found")
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to invalidate access token")


@router.get("/validate_token")
async def check_validate_token(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    try:
        return validate_token(db_session, token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/users/me", response_model=UserResponse)
async def read_users_me(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    return get_user_data(db_session, token)
