"""Component types each kind of gear can carry."""

import modules.gears.gear.schema as gears_schema

BIKE_COMPONENT_TYPES: list[str] = [
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

SHOES_COMPONENT_TYPES: list[str] = [
    "cleats",
    "insoles",
    "laces",
]

RACQUET_COMPONENT_TYPES: list[str] = [
    "basegrip",
    "bumpers",
    "grommets",
    "overgrip",
    "strings",
]

WINDSURF_COMPONENT_TYPES: list[str] = [
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

#: Component types a gear type restricts its components to. A gear type absent here accepts any type.
COMPONENT_TYPES_BY_GEAR_TYPE: dict[gears_schema.GearType, list[str]] = {
    gears_schema.GearType.BIKE: BIKE_COMPONENT_TYPES,
    gears_schema.GearType.SHOES: SHOES_COMPONENT_TYPES,
    gears_schema.GearType.RACQUET: RACQUET_COMPONENT_TYPES,
    gears_schema.GearType.WINDSURF: WINDSURF_COMPONENT_TYPES,
}
