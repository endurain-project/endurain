"""Domain constants for activity thumbnails."""

#: Storage area (domain-owned namespace) activity thumbnails live under. On ``local``
#: it maps to ``{DATA_DIR}/activity_thumbnails``; on S3 it is the object key prefix.
THUMBNAIL_STORAGE_AREA = "activity_thumbnails"
