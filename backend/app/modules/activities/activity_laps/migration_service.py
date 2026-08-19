"""Version-pinned lap operations exposed only to data migrations."""

import modules.activities.activity_laps.crud as activity_laps_crud

create_activity_laps = activity_laps_crud.create_activity_laps
