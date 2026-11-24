"""Exercise titles are stored with ``INSERT ... ON CONFLICT DO NOTHING`` against real PostgreSQL.

The import of a FIT file and a profile import both insert the titles they meet; a pair that already exists, repeats
within the batch or is inserted by a concurrent import must be skipped without failing the caller's transaction or
overwriting the stored name.
"""

import threading

from sqlalchemy import select

import modules.activities.activity_exercise_titles.contracts as titles_contracts
import modules.activities.activity_exercise_titles.crud as titles_crud
import modules.activities.activity_exercise_titles.models as titles_models


def _title(category: int, name: int, step: str) -> titles_contracts.ActivityExerciseTitlesCreate:
    return titles_contracts.ActivityExerciseTitlesCreate(
        exercise_category=category, exercise_name=name, wkt_step_name=step
    )


def _stored(factory) -> dict[tuple[int, int], str]:
    with factory() as db:
        rows = db.execute(select(titles_models.ActivityExerciseTitles)).scalars().all()
        return {(row.exercise_category, row.exercise_name): row.wkt_step_name for row in rows}


def _store(factory, titles) -> None:
    with factory() as db:
        titles_crud.create_activity_exercise_titles(titles, db)
        db.commit()


class TestCreateExerciseTitles:
    def test_new_pairs_are_stored(self, committed_sessions):
        _store(committed_sessions, [_title(1, 1, "Bench Press"), _title(1, 2, "Squat")])

        assert _stored(committed_sessions) == {(1, 1): "Bench Press", (1, 2): "Squat"}

    def test_a_pair_repeated_in_one_batch_is_stored_once(self, committed_sessions):
        _store(committed_sessions, [_title(3, 4, "Row"), _title(3, 4, "Row again"), _title(3, 5, "Curl")])

        stored = _stored(committed_sessions)
        assert set(stored) == {(3, 4), (3, 5)}
        assert stored[(3, 4)] == "Row"

    def test_a_stored_pair_keeps_its_name_when_the_pair_comes_again(self, committed_sessions):
        _store(committed_sessions, [_title(2, 2, "Original")])

        _store(committed_sessions, [_title(2, 2, "Renamed"), _title(2, 3, "Added")])

        assert _stored(committed_sessions) == {(2, 2): "Original", (2, 3): "Added"}

    def test_no_titles_store_nothing(self, committed_sessions):
        _store(committed_sessions, [])

        assert _stored(committed_sessions) == {}

    def test_the_same_category_and_name_are_different_pairs_when_either_differs(self, committed_sessions):
        _store(committed_sessions, [_title(1, 1, "A"), _title(1, 2, "B"), _title(2, 1, "C")])

        assert set(_stored(committed_sessions)) == {(1, 1), (1, 2), (2, 1)}

    def test_concurrent_imports_of_overlapping_pairs_each_commit_and_store_every_pair_once(self, committed_sessions):
        workers = 6
        barrier = threading.Barrier(workers)
        errors: list[Exception] = []

        def import_titles(worker: int) -> None:
            try:
                titles = [_title(7, name, f"worker {worker} step {name}") for name in range(20)]
                barrier.wait()
                _store(committed_sessions, titles)
            except Exception as err:
                errors.append(err)

        threads = [threading.Thread(target=import_titles, args=(worker,)) for worker in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == []
        assert set(_stored(committed_sessions)) == {(7, name) for name in range(20)}
