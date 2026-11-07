"""Domain constants for activity media."""

#: Storage area (domain-owned namespace) activity media lives under. On ``local`` it
#: maps to ``{DATA_DIR}/activity_media``, the directory installs already have; on S3
#: it is the object key prefix.
MEDIA_STORAGE_AREA = "activity_media"
