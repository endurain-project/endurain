import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Form, Response, File, UploadFile, Request
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func, DECIMAL, DateTime
from db.db import get_db_session, Waypoint
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

# @router.post("/waypoints/create")
# async def create_activity(
#     activity_id: int = Form(...),
#     lat: float = Form(...),
#     lon: float = Form(...),
#     ele: float = Form(...),
#     time: str = Form(...),
#     hr: int = Form(...),
#     cad: int = Form(...),
#     token: str = Depends(oauth2_scheme)
# ):
#     from . import sessionController
#     try:
#         # Validate the user's token
#         sessionController.validate_token(token)

#         # Convert the 'time' string to a datetime
#         time = datetime.strptime(time, "%Y-%m-%dT%H:%M:%SZ")
        
#         # Create a new Activity record
#         waypoint = Waypoint(
#             activity_id=activity_id,
#             latitude=lat,
#             longitude=lon,
#             elevation=ele,
#             time=time,
#             heart_rate=hr,
#             cadence=cad
#         )

#         # Store the Activity record in the database
#         with get_db_session() as db_session:
#             db_session.add(waypoint)
#             db_session.commit()
        
#         return {"message": "Waypoint stored successfully"}

#     except JWTError:
#         raise HTTPException(status_code=401, detail="Unauthorized")
#     except Exception as err:
#         print(err)
#         logger.error(err)
#         raise HTTPException(status_code=500, detail="Failed to store activity")

#     #return {"message": "Activity stored successfully"}

class WaypointCreate(BaseModel):
    lat: float
    lon: float
    ele: float
    time: str
    hr: int
    cad: int
    power: int

@router.post("/waypoints/create/{activity_id}")
async def create_activities(
    activity_id: int,
    waypoints: List[WaypointCreate],
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        # Validate the user's token
        sessionController.validate_token(token)

        waypoints_to_create = []
        for waypoint in waypoints:
            # Convert the 'time' string to a datetime
            time = datetime.strptime(waypoint.time, "%Y-%m-%dT%H:%M:%SZ")

            # Create a dictionary for the Waypoint record
            waypoint_data = Waypoint(
                activity_id=activity_id,
                latitude=waypoint.lat,
                longitude=waypoint.lon,
                elevation=waypoint.ele,
                time=time,
                heart_rate=waypoint.hr,
                cadence=waypoint.cad,
                power=waypoint.power
            )
            waypoints_to_create.append(waypoint_data)

        # Store the Waypoint records in the database using bulk_insert_mappings
        with get_db_session() as db_session:
            if waypoints_to_create:
                # Convert model instances to dictionaries
                waypoints_to_create_dict = [waypoint.__dict__ for waypoint in waypoints_to_create]
                db_session.bulk_insert_mappings(Waypoint, waypoints_to_create_dict)
                db_session.commit()
        
        return {"message": "Waypoints stored successfully"}

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        logger.error(err)
        raise HTTPException(status_code=500, detail="Failed to store waypoints")