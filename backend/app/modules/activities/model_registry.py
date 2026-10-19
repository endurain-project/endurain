"""Collect ORM model contributions from installed activities packages."""

import modules.activities.activity.model_registry as activity_model_registry
import modules.activities.activity_exercise_titles.model_registry as activity_exercise_titles_model_registry
import modules.activities.activity_ingestion.model_registry as activity_ingestion_model_registry
import modules.activities.activity_laps.model_registry as activity_laps_model_registry
import modules.activities.activity_media.model_registry as activity_media_model_registry
import modules.activities.activity_sets.model_registry as activity_sets_model_registry
import modules.activities.activity_streams.model_registry as activity_streams_model_registry
import modules.activities.activity_workout_steps.model_registry as activity_workout_steps_model_registry

MODEL_MODULES = (
    *activity_model_registry.MODEL_MODULES,
    *activity_exercise_titles_model_registry.MODEL_MODULES,
    *activity_ingestion_model_registry.MODEL_MODULES,
    *activity_laps_model_registry.MODEL_MODULES,
    *activity_media_model_registry.MODEL_MODULES,
    *activity_sets_model_registry.MODEL_MODULES,
    *activity_streams_model_registry.MODEL_MODULES,
    *activity_workout_steps_model_registry.MODEL_MODULES,
)
