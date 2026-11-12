"""Domain constants for the activities' section of a profile archive."""

#: Name of the activities section, also the key of the ids it would publish.
PROFILE_ARCHIVE_KEY = "activities"

#: Archive entry holding the exported activities.
ACTIVITIES_PATH = "data/activities.json"

#: Archive folder holding each activity's retained source file, keyed ``{activity_id}{ext}``.
ACTIVITY_FILES_FOLDER = "activity_files/"

#: Archive folder holding each activity's media, keyed ``{activity_id}_{suffix}{ext}``.
ACTIVITY_MEDIA_FOLDER = "activity_media/"

#: Fields an archived activity carries that a read resolves for the viewer; they are dropped on import.
ACTIVITY_READ_FIELDS = frozenset({"map_thumbnail_url", "media"})
