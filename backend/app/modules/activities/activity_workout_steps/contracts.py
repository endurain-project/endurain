"""Inter-module shapes for activity workout steps."""

import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema


class ActivityWorkoutStepsCreate(activity_workout_steps_schema.ActivityWorkoutStepsBase):
    """A parsed or archived workout step to persist; the parent id is passed to the store."""
