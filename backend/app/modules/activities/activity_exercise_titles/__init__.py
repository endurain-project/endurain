"""
Activity exercise titles module.

Provides mapping between FIT exercise category/name identifiers and
human-readable workout step names used by activity sets.

Exports:
    - CRUD operations: get_activity_exercise_titles,
      get_public_activity_exercise_titles,
      get_activity_exercise_title_by_exercise_name,
      create_activity_exercise_titles
    - Schemas: ActivityExerciseTitles
    - Models: ActivityExerciseTitles (ORM model)
"""

from .crud import (
    create_activity_exercise_titles,
    get_activity_exercise_title_by_exercise_name,
    get_activity_exercise_titles,
    get_public_activity_exercise_titles,
)
from .models import ActivityExerciseTitles as ActivityExerciseTitlesModel
from .schema import ActivityExerciseTitles

__all__ = [
    # Pydantic schemas
    "ActivityExerciseTitles",
    # Database model
    "ActivityExerciseTitlesModel",
    # CRUD operations
    "create_activity_exercise_titles",
    "get_activity_exercise_title_by_exercise_name",
    "get_activity_exercise_titles",
    "get_public_activity_exercise_titles",
]
