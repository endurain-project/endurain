"""The migration operations keep their historical commit.

CRUD writers only stage now, but a data migration calls each operation once and
moves on, so the ``migration_service`` wrapper owns the commit the CRUD used to.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize(
    ("module", "crud_attr", "crud_target", "call"),
    [
        (
            "modules.activities.activity.migration_service",
            "activity_crud",
            "edit_activity",
            lambda m, db: m.edit_activity(1, 2, MagicMock(), db),
        ),
        (
            "modules.activities.activity.migration_service",
            "activity_crud",
            "set_activity_thumbnail_key",
            lambda m, db: m.set_activity_thumbnail_key(2, "k.png", db),
        ),
        (
            "modules.activities.activity_laps.migration_service",
            "activity_laps_crud",
            "create_activity_laps",
            lambda m, db: m.create_activity_laps([], 2, db),
        ),
        (
            "modules.activities.activity_sets.migration_service",
            "activity_sets_crud",
            "create_activity_sets",
            lambda m, db: m.create_activity_sets([], 2, db),
        ),
        (
            "modules.activities.activity_workout_steps.migration_service",
            "activity_workout_steps_crud",
            "create_activity_workout_steps",
            lambda m, db: m.create_activity_workout_steps([], 2, db),
        ),
        (
            "modules.activities.activity_exercise_titles.migration_service",
            "activity_exercise_titles_crud",
            "create_activity_exercise_titles",
            lambda m, db: m.create_activity_exercise_titles([], db),
        ),
        (
            "modules.activities.activity_media.migration_service",
            "activity_media_crud",
            "edit_activity_media_media_path",
            lambda m, db: m.edit_activity_media_media_path(3, "k.jpg", db),
        ),
        (
            "modules.activities.activity_media.migration_service",
            "activity_media_crud",
            "delete_activity_media",
            lambda m, db: m.delete_activity_media(3, db),
        ),
    ],
)
def test_each_operation_stages_then_commits(module, crud_attr, crud_target, call):
    import importlib

    service = importlib.import_module(module)
    db = MagicMock()

    with patch.object(getattr(service, crud_attr), crud_target) as crud_call:
        call(service, db)

    crud_call.assert_called_once()
    db.commit.assert_called_once()
