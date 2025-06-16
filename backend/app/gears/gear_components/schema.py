from pydantic import BaseModel

GEAR_COMPONENT_TYPES = [
    "back_tire",
    "front_tire",
    "back_tube",
    "front_tube",
    "back_wheel_valve",
    "front_wheel_valve",
    "back_tubeless_sealant",
    "front_tubeless_sealant",
    "back_wheel",
    "front_wheel",
    "back_break_rotor",
    "front_break_rotor",
    "back_break_pads",
    "front_break_pads",
    "back_break_oil",
    "front_break_oil",
    "power_meter",
    "pedals",
    "crankset",
    "cassette",
    "chain",
    "front_shifter",
    "front_derailleur",
    "rear_shifter",
    "rear_derailleur",
    "bottom_bracket",
    "bottle_cage",
    "handlebar",
    "headset",
    "computer_mount",
    "handlebar_tape",
    "grips",
    "stem",
    "seatpost",
    "saddle",
    "fork",
    "frame",
]


class GearComponents(BaseModel):
    id: int | None = None
    user_id: int
    gear_id: int
    type: str
    brand: str | None = None
    model: str | None = None
    purchase_date: str
    retired_date: str | None = None
    is_active: int | None = None
    expected_kms: float | None = None
    purchase_value: float | None = None

    class Config:
        orm_mode = True
        use_enum_values = True
