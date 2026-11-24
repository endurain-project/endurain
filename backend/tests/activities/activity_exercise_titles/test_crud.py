"""Exercise titles are a server-wide catalogue read whole or in id-ordered windows, on the real database."""

import modules.activities.activity_exercise_titles.crud as titles_crud
from tests._factories.activities import make_exercise_titles


class TestRead:
    def test_an_empty_catalogue_reads_and_counts_as_nothing(self, db):
        assert titles_crud.get_activity_exercise_titles(db) == []
        assert titles_crud.get_activity_exercise_titles_page(db, limit=10, offset=0) == []
        assert titles_crud.count_activity_exercise_titles(db) == 0

    def test_every_title_is_read_with_its_stored_fields(self, db):
        make_exercise_titles(db, [(1, 1, "Bench Press"), (1, 2, "Squat")])

        titles = titles_crud.get_activity_exercise_titles(db)

        assert sorted((t.exercise_category, t.exercise_name, t.wkt_step_name) for t in titles) == [
            (1, 1, "Bench Press"),
            (1, 2, "Squat"),
        ]
        assert all(isinstance(t.id, int) for t in titles)

    def test_a_window_follows_id_order_and_the_count_covers_every_title(self, db):
        make_exercise_titles(db, [(1, n, f"Step {n}") for n in range(5)])

        window = titles_crud.get_activity_exercise_titles_page(db, limit=2, offset=1)

        assert [t.exercise_name for t in window] == [1, 2]
        assert window[0].id < window[1].id
        assert titles_crud.count_activity_exercise_titles(db) == 5

    def test_a_window_past_the_end_is_empty(self, db):
        make_exercise_titles(db, [(1, 1, "Only")])

        assert titles_crud.get_activity_exercise_titles_page(db, limit=10, offset=5) == []
