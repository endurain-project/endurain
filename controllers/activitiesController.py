import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Form, Response, File, UploadFile, Request
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func, DECIMAL, DateTime
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
            activity_records = db_session.query(Activity).all()

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

def determine_activity_type(gpx):
    # Default to 'other' if no activity type is specified
    activity_type = 'other'
    
    # Check the GPX 'type' element within the 'trk' section
    if gpx.tracks:
        track = gpx.tracks[0]
        if track.type:
            if track.type.lower() == "running":
                activity_type = 1
            elif track.type.lower() == "trail running":
                activity_type = 2
            else:
                activity_type = 1
    
    return activity_type

def extract_activity_datetime(gpx):
    # Default to None if no datetime is specified
    activity_datetime = None
    
    if gpx.metadata and gpx.metadata.time:
        activity_datetime = gpx.metadata.time.isoformat()
    
    return activity_datetime

@router.post("/activities/create")
async def create_activity(
    distance: int = Form(...),
    name: str = Form(...),
    type: str = Form(...),
    starttime: str = Form(...),
    endtime: str = Form(...),
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
        starttime = datetime.strptime(starttime, "%Y-%m-%dT%H:%M:%SZ")
        # Convert the 'endtime' string to a datetime
        endtime = datetime.strptime(endtime, "%Y-%m-%dT%H:%M:%SZ")

        if type == "running":
            auxType=1
        elif type == "trail running":
            auxType=2
        elif type == "VirtualRun":
            auxType=3
        elif type == "Ride":
            auxType=4
        elif type == "GravelRide":
            auxType=5
        elif type == "EBikeRide":
            auxType=6
        elif type == "VirtualRide":
            auxType=7
        else:
            auxType=10
        
        # Create a new Activity record
        activity = Activity(
            user_id=user_id,
            name=name,
            distance=distance,
            activity_type=auxType,
            start_time=starttime,
            end_time=endtime,
            created_at=func.now()  # Use func.now() to set 'created_at' to the current timestamp
        )

        # Store the Activity record in the database
        with get_db_session() as db_session:
            db_session.add(activity)
            db_session.commit()
            db_session.refresh(activity)  # This will ensure that the activity object is updated with the ID from the database
        
        return {"message": "Activity stored successfully", "id": activity.id}

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        logger.error(err)
        raise HTTPException(status_code=500, detail="Failed to store activity")

    #return {"message": "Activity stored successfully"}