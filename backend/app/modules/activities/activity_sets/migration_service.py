"""Version-pinned workout-set operations exposed only to data migrations."""

import modules.activities.activity_sets.crud as activity_sets_crud

create_activity_sets = activity_sets_crud.create_activity_sets
