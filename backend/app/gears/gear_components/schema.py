from pydantic import BaseModel

GEAR_COMPONENT_TYPES = [
    "back_break_oil",
    "back_break_pads",
    "back_break_rotor",
    "back_tire",
    "back_tube",
    "back_tubeless_sealant",
    "back_wheel",
    "back_wheel_valve",
    "bottom_bracket",
    "bottle_cage",
    "cassette",
    "chain",
    "computer_mount",
    "crank_left_power_meter",
    "crank_right_power_meter",
    "crankset",
    "crankset_power_meter",
    "fork",
    "frame",
    "front_break_oil",
    "front_break_pads",
    "front_break_rotor",
    "front_derailleur",
    "front_shifter",
    "front_tire",
    "front_tube",
    "front_tubeless_sealant",
    "front_wheel",
    "front_wheel_valve",
    "grips",
    "handlebar",
    "handlebar_tape",
    "headset",
    "pedals",
    "pedals_left_power_meter",
    "pedals_power_meter",
    "pedals_right_power_meter",
    "rear_derailleur",
    "rear_shifter",
    "saddle",
    "seatpost",
    "stem",
]


class GearComponents(BaseModel):
    id: int | None = None
    user_id: int
    gear_id: int
    type: str
    brand: str
    model: str
    purchase_date: str
    retired_date: str | None = None
    is_active: bool
    expected_kms: int | None = None
    purchase_value: float | None = None

    class Config:
        orm_mode = True
