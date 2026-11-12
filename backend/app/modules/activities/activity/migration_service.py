"""The activity operations exposed only to data migrations."""

import modules.activities.activity.crud as activity_crud

get_activity_thumbnail_keys = activity_crud.get_activity_thumbnail_keys
replace_activity_thumbnail_keys = activity_crud.replace_activity_thumbnail_keys
