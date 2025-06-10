from pydantic import BaseModel
import enum

class GearComponentType(enum.Enum):
    BACK_TIRE = "back_tire"
    FRONT_TIRE = "front_tire"
    BACK_TUBE = "back_tube"
    FRONT_TUBE = "front_tube"
    BACK_WHEEL_VALVE = "back_wheel_valve"
    FRONT_WHEEL_VALVE = "front_wheel_valve"
    BACK_TUBELESS_SEALANT = "back_tubeless_sealant"
    FRONT_TUBELESS_SEALANT = "front_tubeless_sealant"
    BACK_WHEEL = "back_wheel"
    FRONT_WHEEL = "front_wheel"
    BACK_BREAK_ROTOR = "back_break_rotor"
    FRONT_BREAK_ROTOR = "front_break_rotor"
    BACK_BREAK_PADS = "back_break_pads"
    FRONT_BREAK_PADS = "front_break_pads"
    BACK_BREAK_OIL = "back_break_oil"
    FRONT_BREAK_OIL = "front_break_oil"
    POWER_METER = "power_meter"
    PEDALS = "pedals"
    CRANKSET = "crankset"
    CASSETTE = "cassette"
    CHAIN = "chain"

class GearComponents(BaseModel):
    id: int | None = None
    user_id: int
    gear_id: int
    type: GearComponentType
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