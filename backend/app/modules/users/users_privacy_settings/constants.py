"""Domain constants for user privacy settings."""

#: The integer the activities store for each default-visibility name.
VISIBILITY_LEVELS: dict[str, int] = {
    "public": 0,
    "followers": 1,
    "private": 2,
}

#: What an unset or unrecognized default visibility resolves to. It is the most restrictive level, so
#: a missing or corrupt setting never makes an activity more visible than the user chose.
FALLBACK_VISIBILITY_LEVEL = VISIBILITY_LEVELS["private"]
