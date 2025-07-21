from pydantic import BaseModel


class ActivityLaps(BaseModel):
    id: int | None = None
    activity_id: int | None = None
    start_time: str
    start_position_lat: float | None = None
    start_position_long: float | None = None
    end_position_lat: float | None = None
    end_position_long: float | None = None
    total_elapsed_time: float | None = None
    total_timer_time: float | None = None
    total_distance: float | None = None
    total_cycles: int | None = None
    total_calories: int | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_cadence: int | None = None
    max_cadence: int | None = None
    avg_power: int | None = None
    max_power: int | None = None
    total_ascent: int | None = None
    total_descent: int | None = None
    intensity: str | None = None
    lap_trigger: str | None = None
    sport: str | None = None
    sub_sport: str | None = None
    normalized_power: int | None = None
    total_work: int | None = None
    avg_vertical_oscillation: float | None = None
    avg_stance_time: float | None = None
    avg_fractional_cadence: float | None = None
    max_fractional_cadence: float | None = None
    enhanced_avg_pace: float | None = None
    enhanced_avg_speed: float | None = None
    enhanced_max_pace: float | None = None
    enhanced_max_speed: float | None = None
    enhanced_min_altitude: float | None = None
    enhanced_max_altitude: float | None = None
    avg_vertical_ratio: float | None = None
    avg_step_length: float | None = None

    model_config = {
        "from_attributes": True
    }
