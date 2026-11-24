"""Our bounds on an exercise title, which are the bounds of the columns that store it."""

import pytest
from pydantic import ValidationError

INT4_MAX = 2**31 - 1


def _create(**overrides):
    import modules.activities.activity_exercise_titles.contracts as contracts

    data = {"exercise_category": 1, "exercise_name": 2, "wkt_step_name": "Bench Press"}
    data.update(overrides)
    return contracts.ActivityExerciseTitlesCreate.model_validate(data)


class TestExerciseTitleBounds:
    @pytest.mark.parametrize("field", ["exercise_category", "exercise_name"])
    def test_ids_beyond_the_integer_column_are_rejected(self, field):
        with pytest.raises(ValidationError):
            _create(**{field: INT4_MAX + 1})

    @pytest.mark.parametrize("field", ["exercise_category", "exercise_name"])
    def test_ids_at_the_integer_column_limit_are_accepted(self, field):
        assert getattr(_create(**{field: INT4_MAX}), field) == INT4_MAX

    def test_step_name_over_the_column_length_is_rejected(self):
        with pytest.raises(ValidationError):
            _create(wkt_step_name="x" * 251)
