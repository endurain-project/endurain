"""Version-pinned exercise-title operations exposed only to data migrations."""

import modules.activities.activity_exercise_titles.crud as exercise_titles_crud

create_activity_exercise_titles = exercise_titles_crud.create_activity_exercise_titles
