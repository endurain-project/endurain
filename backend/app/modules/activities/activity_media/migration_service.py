"""The activity-media operations exposed only to data migrations."""

import modules.activities.activity_media.constants as activity_media_constants
import modules.activities.activity_media.crud as activity_media_crud

MEDIA_STORAGE_AREA = activity_media_constants.MEDIA_STORAGE_AREA
get_all_activity_media = activity_media_crud.get_all_activity_media
