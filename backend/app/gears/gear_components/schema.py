from pydantic import BaseModel

BIKE_COMPONENT_TYPES = [
    "back_break_oil",
    "back_break_pads",
    "back_break_rotor",
    "back_tire",
    "back_tube",
    "back_tubeless_sealant",
    "back_tubeless_rim_tape",
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
    "front_tubeless_rim_tape",
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

SHOES_COMPONENT_TYPES = [
    "cleats",
    "insoles",
    "laces",
]

RACQUET_COMPONENT_TYPES = [
    "basegrip",
    "bumpers",
    "grommets",
    "overgrip",
    "strings",
]

WINDSURF_COMPONENT_TYPES = [
    "sail",
    "board",
    "mast",
    "boom",
    "mast_extension",
    "mast_base",
    "mast_universal_joint",
    "fin",
    "footstraps",
    "harness_lines",
    "rigging_lines",
    "footpad",
    "impact_vest",
    "lifeguard_vest",
    "helmet",
    "wing",
    "front_foil",
    "stabilizer",
    "fuselage",
]


class GearComponents(BaseModel):
    """
    Represents a gear component associated with a user and gear.

    Attributes:
        id (int | None): Unique identifier for the gear component.
        user_id (int): Identifier of the user who owns the component.
        gear_id (int): Identifier of the gear to which the component belongs.
        type (str): Type/category of the gear component (e.g., chain, tire).
        brand (str): Brand of the gear component.
        model (str): Model name or number of the gear component.
        purchase_date (str): Date when the component was purchased (ISO format recommended).
        retired_date (str | None): Date when the component was retired, if applicable.
        is_active (bool | None): Indicates if the component is currently active.
        expected_kms (int | None): Expected kilometers the component should last.
        purchase_value (float | None): Purchase value of the component.
    """
    id: int | None = None
    user_id: int
    gear_id: int
    type: str
    brand: str
    model: str
    purchase_date: str
    retired_date: str | None = None
    is_active: bool | None = None
    expected_kms: int | None = None
    purchase_value: float | None = None

    model_config = {
        "from_attributes": True
    }
