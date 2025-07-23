from pydantic import BaseModel


class UsersPrivacySettings(BaseModel):
    id: int | None = None
    user_id: int
    default_activity_visibility: int | None = None
    hide_activity_start_time: bool | None = None
    hide_activity_location: bool | None = None
    hide_activity_map: bool | None = None
    hide_activity_hr: bool | None = None
    hide_activity_power: bool | None = None
    hide_activity_cadence: bool | None = None
    hide_activity_elevation: bool | None = None
    hide_activity_speed: bool | None = None
    hide_activity_pace: bool | None = None
    hide_activity_laps: bool | None = None
    hide_activity_workout_sets_steps: bool | None = None
    hide_activity_gear: bool | None = None

    model_config = {
        "from_attributes": True
    }
