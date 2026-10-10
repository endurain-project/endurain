"""Version-pinned workout-step operations exposed only to data migrations."""

import modules.activities.activity_workout_steps.crud as workout_steps_crud

create_activity_workout_steps = workout_steps_crud.create_activity_workout_steps
