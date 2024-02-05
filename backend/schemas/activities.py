from pydantic import BaseModel


class Activity(BaseModel):
    id: int | None = None
    distance: int
    name: str
    activity_type: str
    start_time: str
    end_time: str
    city: str | None = None
    town: str | None = None
    country: str | None = None
    elevation_gain: int
    elevation_loss: int
    pace: float
    average_speed: float
    average_power: int
    calories: int | None = None
    strava_gear_id: int | None = None
    strava_activity_id: int | None = None

    class Config:
        orm_mode = True


class ActivityDistances(BaseModel):
    swim: float
    bike: float
    run: float


def calculate_activity_distances(activities: list[Activity]):
    """Calculate the distances of the activities for each type of activity (run, bike, swim)"""
    # Initialize the distances
    run = bike = swim = 0.0

    # Calculate the distances
    for activity in activities:
        if activity.activity_type in [1, 2, 3]:
            run += activity.distance
        elif activity.activity_type in [4, 5, 6, 7, 8]:
            bike += activity.distance
        elif activity.activity_type == 9:
            swim += activity.distance

    # Return the distances
    return ActivityDistances(run=run, bike=bike, swim=swim)
