"""What other modules do with exercise titles: store parsed ones, export the catalogue and restore it from a profile."""

import pydantic
import pytest

import modules.activities.activity_exercise_titles.contracts as titles_contracts
import modules.activities.activity_exercise_titles.crud as titles_crud
import modules.activities.activity_exercise_titles.integration_service as titles_integration
from tests._factories.activities import make_exercise_titles

_INT4_MAX = 2**31 - 1


class TestIngestion:
    def test_parsed_titles_are_stored_and_a_known_pair_is_left_alone(self, db):
        make_exercise_titles(db, [(1, 1, "Original")])
        parsed = [
            titles_contracts.ActivityExerciseTitlesCreate(exercise_category=1, exercise_name=1, wkt_step_name="Again"),
            titles_contracts.ActivityExerciseTitlesCreate(exercise_category=1, exercise_name=2, wkt_step_name="New"),
        ]

        titles_integration.ingestion_contributor().persist(parsed, db)

        stored = {
            (t.exercise_category, t.exercise_name): t.wkt_step_name
            for t in titles_crud.get_activity_exercise_titles(db)
        }
        assert stored == {(1, 1): "Original", (1, 2): "New"}

    def test_titles_of_another_shape_are_refused_before_anything_is_stored(self, db):
        with pytest.raises(pydantic.ValidationError):
            titles_integration.ingestion_contributor().persist([{"wkt_step_name": "x"}], db)

        assert titles_crud.count_activity_exercise_titles(db) == 0


class TestProfileArchive:
    def test_the_export_lists_the_whole_catalogue(self, db):
        make_exercise_titles(db, [(1, 1, "A"), (1, 2, "B")])

        exported = titles_integration.profile_global_contributor().export(db)

        assert sorted(t.wkt_step_name for t in exported) == ["A", "B"]

    def test_restore_stores_the_valid_records_and_skips_the_ones_that_do_not_fit(self, db):
        records = [
            {"id": 1, "exercise_category": 1, "exercise_name": 2, "wkt_step_name": "Squat"},
            {"id": 2, "exercise_category": _INT4_MAX + 1, "exercise_name": 2, "wkt_step_name": "Huge"},
            {"id": 3, "exercise_category": 1, "wkt_step_name": "No name id"},
            "not an object",
        ]

        restored = titles_integration.profile_global_contributor().restore(records, db)

        assert restored == 1
        assert [t.wkt_step_name for t in titles_crud.get_activity_exercise_titles(db)] == ["Squat"]

    def test_restoring_nothing_valid_stores_nothing(self, db):
        assert titles_integration.profile_global_contributor().restore([{"bogus": 1}], db) == 0
        assert titles_crud.count_activity_exercise_titles(db) == 0
