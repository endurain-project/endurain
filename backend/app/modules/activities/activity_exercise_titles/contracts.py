"""Inter-module shapes for activity exercise titles."""

import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema


class ActivityExerciseTitlesCreate(activity_exercise_titles_schema.ActivityExerciseTitlesBase):
    """A parsed or archived exercise title to persist."""
