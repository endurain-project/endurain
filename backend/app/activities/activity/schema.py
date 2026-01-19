from pydantic import BaseModel


class Activity(BaseModel):
    id: int | None = None
    user_id: int | None = None
    description: str | None = None
    private_notes: str | None = None
    distance: int
    name: str
    activity_type: int
    start_time: str | None = None
    start_time_tz_applied: str | None = None
    end_time: str | None = None
    end_time_tz_applied: str | None = None
    timezone: str | None = None
    total_elapsed_time: float | None = None
    total_timer_time: float | None = None
    city: str | None = None
    town: str | None = None
    country: str | None = None
    created_at: str | None = None
    created_at_tz_applied: str | None = None
    elevation_gain: int | None = None
    elevation_loss: int | None = None
    pace: float | None = None
    average_speed: float | None = None
    max_speed: float | None = None
    average_power: int | None = None
    max_power: int | None = None
    normalized_power: int | None = None
    average_hr: int | None = None
    max_hr: int | None = None
    average_cad: int | None = None
    max_cad: int | None = None
    workout_feeling: int | None = None
    workout_rpe: int | None = None
    calories: int | None = None
    visibility: int | None = None
    gear_id: int | None = None
    computer_gear_id: int | None = None
    strava_gear_id: str | None = None
    strava_activity_id: int | None = None
    garminconnect_activity_id: int | None = None
    garminconnect_gear_id: str | None = None
    import_info: dict | None = None
    is_hidden: bool = False
    hide_start_time: bool | None = None
    hide_location: bool | None = None
    hide_map: bool | None = None
    hide_hr: bool | None = None
    hide_power: bool | None = None
    hide_cadence: bool | None = None
    hide_elevation: bool | None = None
    hide_speed: bool | None = None
    hide_pace: bool | None = None
    hide_laps: bool | None = None
    hide_workout_sets_steps: bool | None = None
    hide_gear: bool | None = None
    tracker_manufacturer: str | None = None
    tracker_model: str | None = None

    model_config = {"from_attributes": True}


class ActivityDistances(BaseModel):
    run: float
    bike: float
    swim: float
    walk: float
    hike: float
    rowing: float
    snow_ski: float
    snowboard: float
    windsurf: float
    stand_up_paddleboarding: float
    surfing: float
    kayaking: float
    sailing: float
    snowshoeing: float
    inline_skating: float


class ActivityEdit(BaseModel):
    id: int
    description: str | None = None
    private_notes: str | None = None
    name: str
    activity_type: int
    visibility: int | None = None
    is_hidden: bool | None = None
    gear_id: int | None = None
    computer_gear_id: int | None = None
    hide_start_time: bool | None = None
    hide_location: bool | None = None
    hide_map: bool | None = None
    hide_hr: bool | None = None
    hide_power: bool | None = None
    hide_cadence: bool | None = None
    hide_elevation: bool | None = None
    hide_speed: bool | None = None
    hide_pace: bool | None = None
    hide_laps: bool | None = None
    hide_workout_sets_steps: bool | None = None
    hide_gear: bool | None = None
