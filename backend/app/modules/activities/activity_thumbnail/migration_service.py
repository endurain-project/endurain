"""The activity-thumbnail operations exposed only to data migrations."""

import modules.activities.activity_thumbnail.constants as activity_thumbnail_constants
import modules.activities.activity_thumbnail.signing as activity_thumbnail_signing

THUMBNAIL_STORAGE_AREA = activity_thumbnail_constants.THUMBNAIL_STORAGE_AREA
thumbnail_key = activity_thumbnail_signing.thumbnail_key
