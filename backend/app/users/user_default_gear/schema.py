from pydantic import BaseModel


class UserDefaultGear(BaseModel):
    id: int | None
    user_id: int
    run_gear_id: int | None
    trail_run_gear_id: int | None
    virtual_run_gear_id: int | None
    ride_gear_id: int | None
    gravel_ride_gear_id: int | None
    mtb_ride_gear_id: int | None
    virtual_ride_gear_id: int | None
    ows_gear_id: int | None
    walk_gear_id: int | None
    hike_gear_id: int | None
    tennis_gear_id: int | None
    alpine_ski_gear_id: int | None
    nordic_ski_gear_id: int | None
    snowboard_gear_id: int | None
    windsurf_gear_id: int | None

    model_config = {
        "from_attributes": True
    }