"""Domain constants for user default gear."""

#: Activity type code to the default-gear column that holds its gear.
ACTIVITY_TYPE_TO_GEAR_ATTR: dict[int, str] = {
    1: "run_gear_id",
    2: "trail_run_gear_id",
    3: "virtual_run_gear_id",
    4: "ride_gear_id",
    5: "gravel_ride_gear_id",
    6: "mtb_ride_gear_id",
    7: "virtual_ride_gear_id",
    9: "ows_gear_id",
    11: "walk_gear_id",
    12: "hike_gear_id",
    15: "alpine_ski_gear_id",
    16: "nordic_ski_gear_id",
    17: "snowboard_gear_id",
    21: "tennis_gear_id",
    30: "windsurf_gear_id",
    31: "walk_gear_id",
}
