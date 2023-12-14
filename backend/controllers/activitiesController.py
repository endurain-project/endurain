import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func, desc
from db.db import get_db_session, Activity
from jose import jwt, JWTError
#from dotenv import load_dotenv
from pydantic import BaseModel
from datetime import datetime, timedelta
import calendar

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
#load_dotenv("config/.env")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@router.get("/activities/all", response_model=List[dict])
async def read_activities_all(token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            # Query the activities records using SQLAlchemy
            activity_records = (
                db_session.query(Activity).order_by(desc(Activity.start_time)).all()
            )

            # Convert the SQLAlchemy objects to dictionaries
            results = [activity.__dict__ for activity in activity_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return results


@router.get("/activities/useractivities", response_model=List[dict])
async def read_activities_useractivities(token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Query the activities records using SQLAlchemy
            activity_records = (
                db_session.query(Activity)
                .filter(Activity.user_id == user_id)
                .order_by(desc(Activity.start_time))
                .all()
            )

            # Convert the SQLAlchemy objects to dictionaries
            results = [activity.__dict__ for activity in activity_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return results

@router.get("/activities/useractivities/{user_id}/week/{week_number}")
async def read_activities_useractivities_thismonth_number(
    user_id: int, week_number: int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            # Calculate the start of the requested week
            today = datetime.utcnow().date()
            start_of_week = today - timedelta(
                days=(today.weekday() + 7 * week_number)
            )
            end_of_week = start_of_week + timedelta(days=7)

            # Query the count of activities records for the requested week
            activities = (
                db_session.query(Activity)
                .filter(
                    Activity.user_id == user_id,
                    func.date(Activity.start_time) >= start_of_week,
                    func.date(Activity.start_time) <= end_of_week,
                )
            ).all()

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return activities

@router.get("/activities/useractivities/{user_id}/thisweek/distances")
async def read_activities_useractivities_thisweek_distances(
    user_id=int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            # payload = jwt.decode(token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")])
            # user_id = payload.get("id")

            # Calculate the start of the current week
            today = datetime.utcnow().date()
            start_of_week = today - timedelta(
                days=today.weekday()
            )  # Monday is the first day of the week, which is denoted by 0
            end_of_week = start_of_week + timedelta(days=7)

            # Query the activities records for the current week
            activity_records = (
                db_session.query(Activity)
                .filter(
                    Activity.user_id == user_id,
                    func.date(Activity.start_time) >= start_of_week,
                    func.date(Activity.start_time) < end_of_week,
                )
                .order_by(desc(Activity.start_time))
                .all()
            )

            # Initialize distance variables
            run = bike = swim = 0

            # Iterate over the activity records and aggregate the distances
            for activity in activity_records:
                if activity.activity_type in [1, 2, 3]:
                    run += activity.distance
                elif activity.activity_type in [4, 5, 6, 7, 8]:
                    bike += activity.distance
                elif activity.activity_type == 9:
                    swim += activity.distance

            # Prepare the result as JSON
            results = {"run": run, "bike": bike, "swim": swim}

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return results

@router.get("/activities/useractivities/{user_id}/thismonth/distances")
async def read_activities_useractivities_thismonth_distances(
    user_id: int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            # Calculate the start of the current month
            today = datetime.utcnow().date()
            start_of_month = today.replace(day=1)
            end_of_month = start_of_month.replace(
                day=calendar.monthrange(today.year, today.month)[1]
            )

            # Query the activities records for the current month
            activity_records = (
                db_session.query(Activity)
                .filter(
                    Activity.user_id == user_id,
                    func.date(Activity.start_time) >= start_of_month,
                    func.date(Activity.start_time) <= end_of_month,
                )
                .order_by(desc(Activity.start_time))
                .all()
            )

            # Initialize distance variables
            run = bike = swim = 0

            # Iterate over the activity records and aggregate the distances
            for activity in activity_records:
                if activity.activity_type in [1, 2, 3]:
                    run += activity.distance
                elif activity.activity_type in [4, 5, 6, 7, 8]:
                    bike += activity.distance
                elif activity.activity_type == 9:
                    swim += activity.distance

            # Prepare the result as JSON
            results = {"run": run, "bike": bike, "swim": swim}

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return results

@router.get("/activities/useractivities/{user_id}/thismonth/number")
async def read_activities_useractivities_thismonth_number(
    user_id: int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            # Calculate the start of the current month
            today = datetime.utcnow().date()
            start_of_month = today.replace(day=1)
            end_of_month = start_of_month.replace(
                day=calendar.monthrange(today.year, today.month)[1]
            )

            # Query the count of activities records for the current month
            activity_count = (
                db_session.query(func.count(Activity.id))
                .filter(
                    Activity.user_id == user_id,
                    func.date(Activity.start_time) >= start_of_month,
                    func.date(Activity.start_time) <= end_of_month,
                )
                .scalar()
            )

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return {"activity_count": activity_count}

@router.get("/activities/gear/{gearID}", response_model=List[dict])
async def read_activities_gearactivities(
    gearID=int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Query the activities records using SQLAlchemy
            activity_records = (
                db_session.query(Activity)
                .filter(Activity.user_id == user_id, Activity.gear_id == gearID)
                .order_by(desc(Activity.start_time))
                .all()
            )

            # Convert the SQLAlchemy objects to dictionaries
            results = [activity.__dict__ for activity in activity_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return results


@router.get("/activities/all/number")
async def read_activities_all_number(token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            # Query the number of activities records for the user using SQLAlchemy
            activities_count = db_session.query(func.count(Activity.id)).scalar()

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return {0: activities_count}


@router.get("/activities/useractivities/number")
async def read_activities_useractivities_number(token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Query the number of activities records for the user using SQLAlchemy
            activities_count = (
                db_session.query(func.count(Activity.id))
                .filter(Activity.user_id == user_id)
                .scalar()
            )

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return {0: activities_count}


@router.get(
    "/activities/all/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
)
async def read_activities_all_pagination(
    pageNumber: int, numRecords: int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
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
    except NameError as err:
        print(err)

    return results


@router.get(
    "/activities/useractivities/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
)
async def read_activities_useractivities_pagination(
    pageNumber: int, numRecords: int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Use SQLAlchemy to query the gear records with pagination
            activity_records = (
                db_session.query(Activity)
                .filter(Activity.user_id == user_id)
                .order_by(desc(Activity.start_time))
                .offset((pageNumber - 1) * numRecords)
                .limit(numRecords)
                .all()
            )

            # Convert the SQLAlchemy results to a list of dictionaries
            results = [record.__dict__ for record in activity_records]

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return results


# Get gear from id
@router.get("/activities/{id}/activityfromid", response_model=List[dict])
async def read_activities_activityFromId(id: int, token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        sessionController.validate_token(token)
        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Use SQLAlchemy to query the gear record by ID
            activity_record = (
                db_session.query(Activity)
                .filter(Activity.id == id, Activity.user_id == user_id)
                .first()
            )

            # Convert the SQLAlchemy result to a list of dictionaries
            if activity_record:
                results = [activity_record.__dict__]
            else:
                results = []

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)

    return results


@router.put("/activities/{activity_id}/addgear/{gear_id}")
async def activity_add_gear(
    activity_id: int, gear_id: int, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        sessionController.validate_token(token)

        # Use SQLAlchemy to query and delete the gear record
        with get_db_session() as db_session:
            activity_record = (
                db_session.query(Activity).filter(Activity.id == activity_id).first()
            )

            if activity_record:
                activity_record.gear_id = gear_id

                # Commit the transaction
                db_session.commit()
                return {"message": "Gear added to activity successfully"}
            else:
                raise HTTPException(status_code=404, detail="Activity not found")

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        raise HTTPException(status_code=500, detail="Failed to add gear to activity")

    return {"message": f"Gear added to {activity_id}"}


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
    averageSpeed: float
    averagePower: int
    strava_id: Optional[int]


@router.post("/activities/create")
async def create_activity(
    activity_data: CreateActivityRequest, token: str = Depends(oauth2_scheme)
):
    from . import sessionController

    try:
        # Validate the user's token
        sessionController.validate_token(token)

        # get user_id
        payload = jwt.decode(
            token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
        )
        user_id = payload.get("id")

        # Convert the 'starttime' string to a datetime
        # starttime = datetime.strptime(activity_data.starttime, "%Y-%m-%dT%H:%M:%SZ")
        starttime = parse_timestamp(activity_data.starttime)
        # Convert the 'endtime' string to a datetime
        # endtime = datetime.strptime(activity_data.endtime, "%Y-%m-%dT%H:%M:%SZ")
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
            "open_water_swimming": 8,
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
            pace=activity_data.pace,
            average_speed=activity_data.averageSpeed,
            average_power=activity_data.averagePower,
            strava_activity_id=activity_data.strava_id,
        )

        # Store the Activity record in the database
        with get_db_session() as db_session:
            db_session.add(activity)
            db_session.commit()
            db_session.refresh(
                activity
            )  # This will ensure that the activity object is updated with the ID from the database

        # return {"message": "Activity stored successfully", "id": activity.id}
        return {"message": "Activity stored successfully"}

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        logger.error(err)
        raise HTTPException(status_code=500, detail="Failed to store activity")

    # return {"message": "Activity stored successfully"}


def parse_timestamp(timestamp_string):
    try:
        # Try to parse with milliseconds
        return datetime.strptime(timestamp_string, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        # If milliseconds are not present, use a default value of 0
        return datetime.strptime(timestamp_string, "%Y-%m-%dT%H:%M:%SZ")


# Define an HTTP PUT route to delete an activity gear
@router.put("/activities/{activity_id}/deletegear")
async def delete_activity_gear(activity_id: int, token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        with get_db_session() as db_session:
            # get user_id
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Query the database to find the user by their ID
            activity = (
                db_session.query(Activity)
                .filter(Activity.id == activity_id, Activity.user_id == user_id)
                .first()
            )

            # Check if the user with the given ID exists
            if not activity:
                raise HTTPException(status_code=404, detail="Activity not found")

            # Set the user's photo paths to None to delete the photo
            activity.gear_id = None

            # Commit the changes to the database
            db_session.commit()
    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        # Handle any other unexpected exceptions
        print(err)
        raise HTTPException(status_code=500, detail="Failed to update activity gear")

    # Return a success message
    return {"message": f"Activity gear {activity_id} has been deleted"}


@router.delete("/activities/{activity_id}/delete")
async def delete_activity(activity_id: int, token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        sessionController.validate_token(token)

        # Use SQLAlchemy to query and delete the gear record
        with get_db_session() as db_session:
            # get user_id
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            activity_record = (
                db_session.query(Activity)
                .filter(Activity.id == activity_id, Activity.user_id == user_id)
                .first()
            )

            if activity_record:
                # Check for existing dependencies (uncomment if needed)
                # Example: Check if there are dependencies in another table
                # if db_session.query(OtherModel).filter(OtherModel.gear_id == gear_id).count() > 0:
                #     response.status_code = 409
                #     return {"detail": "Cannot delete gear due to existing dependencies"}

                # Delete the gear record
                db_session.delete(activity_record)

                # Commit the transaction
                db_session.commit()
                return {"message": f"Activity {activity_id} has been deleted"}
            else:
                raise HTTPException(status_code=404, detail="Activity not found")

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        print(err)
        raise HTTPException(status_code=500, detail="Failed to delete activity")

    return {"message": f"Activity {activity_id} has been deleted"}
