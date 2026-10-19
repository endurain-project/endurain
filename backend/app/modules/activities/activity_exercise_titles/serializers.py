"""ORM↔schema transformation for activity exercise titles.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.activities.activity_exercise_titles.models as activity_exercise_titles_models
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema


def to_read_schema(
    orm_title: activity_exercise_titles_models.ActivityExerciseTitles,
) -> activity_exercise_titles_schema.ActivityExerciseTitlesRead:
    """Convert an ORM row to its read schema.

    Args:
        orm_title: The ORM model instance.

    Returns:
        An ActivityExerciseTitles schema instance.
    """
    return activity_exercise_titles_schema.ActivityExerciseTitlesRead.model_validate(orm_title)
