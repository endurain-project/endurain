import os
from zoneinfo import ZoneInfo

from datetime import datetime

import activities.activity_laps.schema as activity_laps_schema

import activities.activity.schema as activities_schema

def serialize_activity_lap(activity: activities_schema.Activity, activity_lap: activity_laps_schema.ActivityLaps):
    def make_aware_and_format(dt, timezone):
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(timezone).strftime("%Y-%m-%dT%H:%M:%S")

    timezone = (
        ZoneInfo(activity.timezone)
        if activity.timezone
        else ZoneInfo(os.environ.get("TZ"))
    )

    activity_lap.start_time = make_aware_and_format(activity_lap.start_time, timezone)

    return activity_lap