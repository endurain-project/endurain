"""Version-pinned activity operations exposed only to data migrations."""

import modules.activities.activity.crud as activity_crud

get_all_activities = activity_crud.get_all_activities
get_all_activities_for_migration = activity_crud.get_all_activities_for_migration
edit_activity = activity_crud.edit_activity
get_activity_by_id = activity_crud.get_activity_by_id
get_activities_with_legacy_thumbnail_path = activity_crud.get_activities_with_legacy_thumbnail_path
set_activity_thumbnail_path = activity_crud.set_activity_thumbnail_path
