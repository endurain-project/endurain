"""Collect ORM model contributions from installed activities packages."""

import modules.activities.activity.model_registry as activity_models
import modules.activities.activity_exercise_titles.model_registry as exercise_title_models
import modules.activities.activity_ingestion.model_registry as ingestion_models
import modules.activities.activity_laps.model_registry as lap_models
import modules.activities.activity_media.model_registry as media_models
import modules.activities.activity_sets.model_registry as set_models
import modules.activities.activity_streams.model_registry as stream_models
import modules.activities.activity_workout_steps.model_registry as workout_step_models

MODEL_MODULES = (
    *activity_models.MODEL_MODULES,
    *exercise_title_models.MODEL_MODULES,
    *ingestion_models.MODEL_MODULES,
    *lap_models.MODEL_MODULES,
    *media_models.MODEL_MODULES,
    *set_models.MODEL_MODULES,
    *stream_models.MODEL_MODULES,
    *workout_step_models.MODEL_MODULES,
)
