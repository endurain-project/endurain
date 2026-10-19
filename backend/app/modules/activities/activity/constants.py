"""Activity type mappings shared across the activities module.

The id↔name maps have a single, dependency-free home that any submodule (crud,
dependencies, summaries, the file-import parsers) can import without pulling in
the ingestion/parsing machinery.
"""

from enum import IntEnum, StrEnum


class ActivityVisibilityLevel(IntEnum):
    """Who may see an activity, as stored in ``activities.visibility``.

    Attributes:
        PUBLIC: Anyone, including unauthenticated viewers of public links.
        FOLLOWERS: Accepted followers of the owner.
        PRIVATE: The owner only.
    """

    PUBLIC = 0
    FOLLOWERS = 1
    PRIVATE = 2


# Global Activity Type Mappings (ID to Name)
ACTIVITY_ID_TO_NAME = {
    1: "Run",
    2: "Trail run",
    3: "Virtual run",
    4: "Ride",
    5: "Gravel ride",
    6: "MTB ride",
    7: "Virtual ride",
    8: "Lap swimming",
    9: "Open water swimming",
    10: "Workout",
    11: "Walk",
    12: "Hike",
    13: "Rowing",
    14: "Yoga",
    15: "Alpine ski",
    16: "Nordic ski",
    17: "Snowboard",
    18: "Transition",
    19: "Strength training",
    20: "Crossfit",
    21: "Tennis",
    22: "TableTennis",
    23: "Badminton",
    24: "Squash",
    25: "Racquetball",
    26: "Pickleball",
    27: "Commuting ride",
    28: "Indoor ride",
    29: "Mixed surface ride",
    30: "Windsurf",
    31: "Indoor walking",
    32: "Stand up paddling",
    33: "Surf",
    34: "Track run",
    35: "E-Bike ride",
    36: "E-Mountain Bike ride",
    37: "Ice Skate",
    38: "Soccer",
    39: "Padel",
    40: "Treadmill",
    41: "Cardio training",
    42: "Kayaking",
    43: "Sailing",
    44: "Snow shoeing",
    45: "Inline skating",
    46: "HIIT",
    47: "Jump rope",
    # Add other mappings as needed based on the full list in define_activity_type comments if required
    # "AlpineSki",
    # "BackcountrySki",
    # "Badminton",
    # "Canoeing",
    # "Crossfit",
    # "EBikeRide",
    # "Elliptical",
    # "EMountainBikeRide",
    # "Golf",
    # "GravelRide",
    # "Handcycle",
    # "HighIntensityIntervalTraining",
    # "Hike",
    # "IceSkate",
    # "InlineSkate",
    # "Kayaking",
    # "Kitesurf",
    # "MountainBikeRide",
    # "NordicSki",
    # "Pickleball",
    # "Pilates",
    # "Racquetball",
    # "Ride",
    # "RockClimbing",
    # "RollerSki",
    # "Rowing",
    # "Run",
    # "Sail",
    # "Skateboard",
    # "Snowboard",
    # "Snowshoe",
    # "Soccer",
    # "Squash",
    # "StairStepper",
    # "StandUpPaddling",
    # "Surfing",
    # "Swim",
    # "TableTennis",
    # "Tennis",
    # "TrailRun",
    # "Velomobile",
    # "VirtualRide",
    # "VirtualRow",
    # "VirtualRun",
    # "Walk",
    # "WeightTraining",
    # "Wheelchair",
    # "Windsurf",
    # "Workout",
    # "Yoga"
}

# Global Activity Type Mappings (Name to ID) - Case Insensitive Keys
ACTIVITY_NAME_TO_ID = {name.lower(): activity_type_id for activity_type_id, name in ACTIVITY_ID_TO_NAME.items()}

#: Activity types recorded on a virtual platform (Zwift and the like). Any GPS
#: position such a file carries describes the platform's synthetic route rather
#: than where the athlete actually was, so it must not be used to resolve their
#: timezone. Named for the question the parsers ask, so both share one answer.
VIRTUAL_ACTIVITY_TYPES = frozenset({3, 7})

#: The sport each activity type belongs to. The activities module owns the
#: activity-type vocabulary, so it owns the grouping over it too: a consumer that
#: needs "which types count as running?" asks here instead of keeping its own
#: copy of the ids. ``modules.users.users_goals`` had one, and the two agreed on
#: running, cycling and swimming while quietly disagreeing about walking — the
#: kind of divergence that shows up as an activity counting towards a sport's
#: totals but not towards a goal for the same sport.
#:
#: Keys match the per-sport attribute names on
#: :class:`~modules.activities.activity.schema.ActivityStatsRead`.
ACTIVITY_TYPES_BY_SPORT: dict[str, tuple[int, ...]] = {
    "run": (1, 2, 3, 34, 40),
    "bike": (4, 5, 6, 7, 27, 28, 29, 35, 36),
    "swim": (8, 9),
    "walk": (11, 31),
    "hike": (12,),
    "rowing": (13,),
    "snow_ski": (15, 16),
    "snowboard": (17,),
    "windsurf": (30,),
    "stand_up_paddleboarding": (32,),
    "surfing": (33,),
    "kayaking": (42,),
    "sailing": (43,),
    "snowshoeing": (44,),
    "inline_skating": (45,),
}


class ActivitySortField(StrEnum):
    """Sort keys the activity list endpoints accept, in the order they appear in the UI.

    A real enum so FastAPI validates the query parameter and publishes the accepted values.
    """

    type = "type"
    name = "name"
    location = "location"
    start_time = "start_time"
    duration = "duration"
    distance = "distance"
    pace = "pace"
    calories = "calories"
    elevation = "elevation"
    average_hr = "average_hr"


#: The activity columns each sort key orders by (highest precedence first). One declaration
#: feeds both the transport validator and the query's ``SORT_MAP``, so a key the endpoint
#: accepts always has an ordering.
#:
#: Column *names* rather than ORM attributes: a contract-layer constant must not
#: import the persistence layer. ``crud`` resolves them against the model.
ACTIVITY_SORT_FIELDS: dict[ActivitySortField, tuple[str, ...]] = {
    ActivitySortField.type: ("activity_type",),
    ActivitySortField.name: ("name",),
    ActivitySortField.location: ("country", "city", "town"),
    ActivitySortField.start_time: ("start_time",),
    ActivitySortField.duration: ("total_timer_time",),
    ActivitySortField.distance: ("distance",),
    ActivitySortField.pace: ("pace",),
    ActivitySortField.calories: ("calories",),
    ActivitySortField.elevation: ("elevation_gain",),
    ActivitySortField.average_hr: ("average_hr",),
}

#: The sort key applied when a request names none.
DEFAULT_ACTIVITY_SORT_FIELD = ActivitySortField.start_time


class ActivitySortOrder(StrEnum):
    """Accepted sort directions.

    Attributes:
        ASC: Ascending.
        DESC: Descending.
    """

    ASC = "asc"
    DESC = "desc"


# Add specific variations found in define_activity_type
ACTIVITY_NAME_TO_ID.update(
    {
        "running": 1,
        "trail running": 2,
        "trailrun": 2,
        "trail": 2,
        "virtualrun": 3,
        "cycling": 4,
        "biking": 4,
        "road": 4,
        "gravelride": 5,
        "gravel_cycling": 5,
        "mountainbikeride": 6,
        "mountain": 6,
        "virtualride": 7,
        "virtual_ride": 7,
        "swim": 8,
        "swimming": 8,
        "lap_swimming": 8,
        "open_water_swimming": 9,
        "open_water": 9,
        "walk": 11,
        "walking": 11,
        "hike": 12,
        "hiking": 12,
        "rowing": 13,
        "indoor_rowing": 13,
        "yoga": 14,
        "alpineski": 15,
        "resort_skiing": 15,
        "alpine_skiing": 15,
        "nordicski": 16,
        "snowboard": 17,
        "transition": 18,
        "strength_training": 19,
        "weighttraining": 19,
        "crossfit": 20,
        "tennis": 21,
        "tabletennis": 22,
        "badminton": 23,
        "squash": 24,
        "racquetball": 25,
        "pickleball": 26,
        "commuting_ride": 27,
        "indoor_ride": 28,
        "indoor_cycling": 28,
        "mixed_surface_ride": 29,
        "windsurf": 30,
        "windsurfing": 30,
        "indoor_walking": 31,
        "stand_up_paddleboarding": 32,
        "standuppaddling": 32,
        "surfing": 33,
        "track running": 34,
        "trackrun": 34,
        "track": 34,
        "ebikeride": 35,
        "e_bike": 35,
        "ebike": 35,
        "e_bike_ride": 35,
        "e_bike_fitness": 35,
        "emountainbikeride": 36,
        "e_bike_mountain": 36,
        "ebikemountain": 36,
        "e_bike_mountain_ride": 36,
        "ebikemountainride": 36,
        "iceskate": 37,
        "soccer": 38,
        "padel": 39,
        "padelball": 39,
        "paddelball": 39,
        "treadmill": 40,
        "indoor_running": 40,
        "cardio_training": 41,
        "kayaking": 42,
        "sailing": 43,
        "sail": 43,
        "snowshoeing": 44,
        "snowshoe": 44,
        "inline_skating": 45,
        "inlineskate": 45,
        "hiit": 46,
        "high_intensity_interval_training": 46,
        "highintensityintervaltraining": 46,
        "jump_rope": 47,
        "jumprope": 47,
    }
)


def define_activity_type(activity_type_name: str) -> int:
    """Map an activity-type name to its id (case-insensitive).

    Args:
        activity_type_name: The provider/parser sport-type name.

    Returns:
        The matching activity-type id, or ``10`` (Workout) when the name is not
        recognised or is not a string.
    """
    default_type_id = 10

    if isinstance(activity_type_name, str):
        return ACTIVITY_NAME_TO_ID.get(activity_type_name.lower(), default_type_id)
    return default_type_id


def set_activity_name_based_on_activity_type(activity_type_id: int) -> str:
    """Map an activity-type id to a display name.

    Args:
        activity_type_id: The activity-type id.

    Returns:
        The mapped name; unknown ids and ``10`` yield ``"Workout"``, every other
        type gets a ``" workout"`` suffix (e.g. ``"Run workout"``).
    """
    mapping = ACTIVITY_ID_TO_NAME.get(activity_type_id, "Workout")

    return mapping + " workout" if mapping != "Workout" else mapping
