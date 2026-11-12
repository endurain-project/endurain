"""The activity-media operations exposed only to data migrations."""

import modules.activities.activity_media.constants as activity_media_constants
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.service as activity_media_service

MEDIA_STORAGE_AREA = activity_media_constants.MEDIA_STORAGE_AREA
get_all_activity_media = activity_media_crud.get_all_activity_media
replace_activity_media_paths = activity_media_crud.replace_activity_media_paths
media_key = activity_media_service.media_key
