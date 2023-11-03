import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Form, Response
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func
from db.db import get_db_session, Gear
from jose import jwt, JWTError
from dotenv import load_dotenv
import mysql.connector.errors
from urllib.parse import unquote
from pydantic import BaseModel

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
load_dotenv('config/.env')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.get("/gear/all", response_model=List[dict])
async def read_gear_all(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Query the gear records using SQLAlchemy
            gear_records = db_session.query(Gear).filter(Gear.user_id == user_id).order_by(Gear.nickname).all()

            # Convert the SQLAlchemy objects to dictionaries
            results = [gear.__dict__ for gear in gear_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

@router.get("/gear/all/running", response_model=List[dict])
async def read_gear_all_running(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Query the gear records using SQLAlchemy
            gear_records = db_session.query(Gear).filter(
                Gear.gear_type == 2,
                Gear.user_id == user_id
                ).order_by(Gear.nickname).all()

            # Convert the SQLAlchemy objects to dictionaries
            results = [gear.__dict__ for gear in gear_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

@router.get("/gear/all/cycling", response_model=List[dict])
async def read_gear_all_cycling(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Query the gear records using SQLAlchemy
            gear_records = db_session.query(Gear).filter(
                Gear.gear_type == 1,
                Gear.user_id == user_id
                ).order_by(Gear.nickname).all()

            # Convert the SQLAlchemy objects to dictionaries
            results = [gear.__dict__ for gear in gear_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

@router.get("/gear/all/swimming", response_model=List[dict])
async def read_gear_all_swimming(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Query the gear records using SQLAlchemy
            gear_records = db_session.query(Gear).filter(
                Gear.gear_type == 3,
                Gear.user_id == user_id
                ).order_by(Gear.nickname).all()

            # Convert the SQLAlchemy objects to dictionaries
            results = [gear.__dict__ for gear in gear_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

@router.get("/gear/number")
async def read_gear_number(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Query the number of gear records for the user using SQLAlchemy
            gear_count = db_session.query(func.count(Gear.id)).filter(Gear.user_id == user_id).scalar()

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return {0: gear_count}

@router.get("/gear/all/pagenumber/{pageNumber}/numRecords/{numRecords}", response_model=List[dict])
async def read_gear_all_pagination(
    pageNumber: int,
    numRecords: int,
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Use SQLAlchemy to query the gear records with pagination
            gear_records = (
                db_session.query(Gear)
                .filter(Gear.user_id == user_id)
                .order_by(Gear.nickname.asc())
                .offset((pageNumber - 1) * numRecords)
                .limit(numRecords)
                .all()
            )

            # Convert the SQLAlchemy results to a list of dictionaries
            results = [record.__dict__ for record in gear_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results


@router.get("/gear/{nickname}/gearfromnickname", response_model=List[dict])
async def read_gear_gearFromNickname(nickname: str, token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Define a search term
            partial_nickname = unquote(nickname).replace("+", " ")

            # Use SQLAlchemy to query the gear records by nickname
            gear_records = (
                db_session.query(Gear)
                .filter(Gear.nickname.like(f"%{partial_nickname}%"), Gear.user_id == user_id)
                .all()
            )

            # Convert the SQLAlchemy results to a list of dictionaries
            results = [record.__dict__ for record in gear_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results


# Get gear from id
@router.get("/gear/{id}/gearfromid", response_model=List[dict])
async def read_gear_gearFromId(id: int, token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Use SQLAlchemy to query the gear record by ID
            gear_record = (
                db_session.query(Gear)
                .filter(Gear.id == id, Gear.user_id == user_id)
                .first()
            )

            # Convert the SQLAlchemy result to a list of dictionaries
            if gear_record:
                results = [gear_record.__dict__]
            else:
                results = []

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

class CreateGearRequest(BaseModel):
    brand: Optional[str]
    model: Optional[str]
    nickname: str
    gear_type: int
    date: str

@router.post("/gear/create")
async def create_gear(
    gear: CreateGearRequest, 
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        sessionController.validate_token(token)

        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        user_id = payload.get("id")

        with get_db_session() as db_session:
            # Use SQLAlchemy to create a new gear record
            gear_record = Gear(
                brand=unquote(gear.brand).replace("+", " "),
                model=unquote(gear.model).replace("+", " "),
                nickname=unquote(gear.nickname).replace("+", " "),
                gear_type=gear.gear_type,
                user_id=user_id,
                created_at=gear.date,
                is_active=True,
            )

            # Add the gear record to the database using SQLAlchemy
            db_session.add(gear_record)
            db_session.commit()

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)
        raise HTTPException(status_code=500, detail="Failed to create gear")

    return {"message": "Gear added successfully"}

class EditGearRequest(BaseModel):
    brand: Optional[str]
    model: Optional[str]
    nickname: str
    gear_type: int
    date: str
    is_active: int

@router.put("/gear/{gear_id}/edit")
async def edit_gear(
    gear_id: int,
    gear: EditGearRequest,
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        sessionController.validate_token(token)

        # Use SQLAlchemy to query and update the gear record
        with get_db_session() as db_session:
            gear_record = db_session.query(Gear).filter(Gear.id == gear_id).first()

            if gear_record:
                if gear.brand is not None:
                    gear_record.brand = unquote(gear.brand).replace("+", " ")
                if gear.model is not None:
                    gear_record.model = unquote(gear.model).replace("+", " ")
                gear_record.nickname = unquote(gear.nickname).replace("+", " ")
                gear_record.gear_type = gear.gear_type
                gear_record.created_at = gear.date
                gear_record.is_active = gear.is_active

                # Commit the transaction
                db_session.commit()
                return {"message": "Gear edited successfully"}
            else:
                raise HTTPException(status_code=404, detail="Gear not found")

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        raise HTTPException(status_code=500, detail="Failed to edit gear")

    return {"message": "Gear edited successfully"}

@router.delete("/gear/{gear_id}/delete")
async def delete_gear(gear_id: int, response: Response, token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)

        # Use SQLAlchemy to query and delete the gear record
        with get_db_session() as db_session:
            gear_record = db_session.query(Gear).filter(Gear.id == gear_id).first()

            if gear_record:
                # Check for existing dependencies (uncomment if needed)
                # Example: Check if there are dependencies in another table
                # if db_session.query(OtherModel).filter(OtherModel.gear_id == gear_id).count() > 0:
                #     response.status_code = 409
                #     return {"detail": "Cannot delete gear due to existing dependencies"}

                # Delete the gear record
                db_session.delete(gear_record)

                # Commit the transaction
                db_session.commit()
                return {"message": f"Gear {gear_id} has been deleted"}
            else:
                raise HTTPException(status_code=404, detail="Gear not found")

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        raise HTTPException(status_code=500, detail="Failed to delete gear")

    return {"message": f"Gear {gear_id} has been deleted"}
