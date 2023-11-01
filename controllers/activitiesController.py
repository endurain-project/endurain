import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Response, File, UploadFile, Request
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func, DECIMAL, DateTime, desc
from db.db import get_db_session, Activity
from jose import jwt, JWTError
from dotenv import load_dotenv
import mysql.connector.errors
from urllib.parse import unquote
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
load_dotenv('config/.env')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.get("/activities/all", response_model=List[dict])
async def read_activities_all(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            #payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            #user_id = payload.get("id")

            # Query the activities records using SQLAlchemy
            activity_records = db_session.query(Activity).order_by(desc(Activity.start_time)).all()

            # Convert the SQLAlchemy objects to dictionaries
            results = [activity.to_dict() for activity in activity_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

@router.get("/activities/number")
async def read_activities_number(token: str = Depends(oauth2_scheme)):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            #payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            #user_id = payload.get("id")

            # Query the number of activities records for the user using SQLAlchemy
            activities_count = db_session.query(func.count(Activity.id)).scalar()

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return {0: activities_count}

@router.get("/activities/all/pagenumber/{pageNumber}/numRecords/{numRecords}", response_model=List[dict])
async def read_activities_all_pagination(
    pageNumber: int,
    numRecords: int,
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            #payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            #user_id = payload.get("id")

            # Use SQLAlchemy to query the gear records with pagination
            activity_records = (
                db_session.query(Activity)
                .order_by(desc(Activity.start_time))
                .offset((pageNumber - 1) * numRecords)
                .limit(numRecords)
                .all()
            )

            # Convert the SQLAlchemy results to a list of dictionaries
            results = [record.__dict__ for record in activity_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

    return results

class CreateActivityRequest(BaseModel):
    distance: int
    name: str
    type: str
    starttime: str
    endtime: str
    city: Optional[str]
    town: Optional[str]
    country: Optional[str]
    waypoints: List[dict]
    elevationGain: int
    elevationLoss: int
    pace: float

@router.post("/activities/create")
async def create_activity(
    activity_data: CreateActivityRequest,
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        # Validate the user's token
        sessionController.validate_token(token)

        # get user_id
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
        user_id = payload.get("id")

        # Convert the 'starttime' string to a datetime
        #starttime = datetime.strptime(activity_data.starttime, "%Y-%m-%dT%H:%M:%SZ")
        starttime = parse_timestamp(activity_data.starttime)
        # Convert the 'endtime' string to a datetime
        #endtime = datetime.strptime(activity_data.endtime, "%Y-%m-%dT%H:%M:%SZ")
        endtime = parse_timestamp(activity_data.endtime)

        auxType = 10  # Default value
        type_mapping = {
            "running": 1,
            "trail running": 2,
            "VirtualRun": 3,
            "cycling": 4,
            "Ride": 4,
            "GravelRide": 5,
            "EBikeRide": 6,
            "VirtualRide": 7,
            "virtual_ride": 7,
            "swimming": 8,
            "open_water_swimming": 8
        }
        auxType = type_mapping.get(activity_data.type, 10)
        
        # Create a new Activity record
        activity = Activity(
            user_id=user_id,
            name=activity_data.name,
            distance=activity_data.distance,
            activity_type=auxType,
            start_time=starttime,
            end_time=endtime,
            city=activity_data.city,
            town=activity_data.town,
            country=activity_data.country,
            created_at=func.now(),  # Use func.now() to set 'created_at' to the current timestamp
            waypoints=activity_data.waypoints,
            elevation_gain=activity_data.elevationGain,
            elevation_loss=activity_data.elevationLoss,
            pace=activity_data.pace
        )

        # Store the Activity record in the database
        with get_db_session() as db_session:
            db_session.add(activity)
            db_session.commit()
            db_session.refresh(activity)  # This will ensure that the activity object is updated with the ID from the database
        
        #return {"message": "Activity stored successfully", "id": activity.id}
        return {"message": "Activity stored successfully"}

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        logger.error(err)
        raise HTTPException(status_code=500, detail="Failed to store activity")

    #return {"message": "Activity stored successfully"}

def parse_timestamp(timestamp_string):
    try:
        # Try to parse with milliseconds
        return datetime.strptime(timestamp_string, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        # If milliseconds are not present, use a default value of 0
        return datetime.strptime(timestamp_string, "%Y-%m-%dT%H:%M:%SZ")