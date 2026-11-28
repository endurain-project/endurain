"""Matching a recording to an effort the owner already has: what is the same effort, and what a match does."""

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.events as activity_events
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.models as activity_models
import modules.activities.activity.source_crud as activity_source_crud
from tests._factories.activities import (
    DEFAULT_START,
    make_activity_at,
    make_multisport,
    make_parsed_activity,
    make_source,
)
from tests._factories.users import make_user
from tests._helpers import concurrency

_Type = activity_constants.ActivityType
_Outcome = activity_contracts.IngestOutcome
_FILE = "f" * 64


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


def _recording(user_id, *, start=DEFAULT_START, minutes=60, sport=_Type.RUN, source=None, **fields):
    return make_parsed_activity(
        user_id,
        source=source,
        start=start,
        end_time=start + timedelta(minutes=minutes),
        activity_type=sport.stored,
        **fields,
    )


def _file(content_hash: str, precedence: int = 2) -> activity_contracts.ImportSource:
    return activity_contracts.ImportSource(kind="upload", content_hash=content_hash, precedence=precedence)


def _stored_with_file(db, owner, content_hash="a" * 64, precedence=2, **fields):
    result = ingestion_service.ingest(_recording(owner.id, source=_file(content_hash, precedence), **fields), db)
    assert result.outcome is _Outcome.CREATED
    return result.activity


def _sources_of(db, activity_id):
    rows = db.scalars(
        select(activity_models.ActivitySource).where(activity_models.ActivitySource.activity_id == activity_id)
    ).all()
    return sorted((row.kind, row.precedence) for row in rows)


class TestWhatIsTheSameEffort:
    def test_a_recording_overlapping_by_80_percent_of_the_shorter_is_attached(self, db, owner):
        stored = _stored_with_file(db, owner, minutes=60)

        result = ingestion_service.ingest(
            _recording(owner.id, start=DEFAULT_START + timedelta(minutes=12), minutes=60, source=_file("b" * 64)), db
        )

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, stored.id)

    def test_a_recording_overlapping_by_less_is_a_new_activity(self, db, owner):
        stored = _stored_with_file(db, owner, minutes=60)

        result = ingestion_service.ingest(
            _recording(owner.id, start=DEFAULT_START + timedelta(minutes=12.5), minutes=60, source=_file("b" * 64)), db
        )

        assert result.outcome is _Outcome.CREATED
        assert result.activity.id != stored.id

    def test_a_short_recording_inside_a_long_one_is_attached(self, db, owner):
        stored = _stored_with_file(db, owner, minutes=180)

        result = ingestion_service.ingest(
            _recording(owner.id, start=DEFAULT_START + timedelta(minutes=60), minutes=20, source=_file("b" * 64)), db
        )

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, stored.id)

    def test_a_recording_of_no_length_matches_only_one_that_starts_in_its_second(self, db, owner):
        stored = _stored_with_file(db, owner)

        same = ingestion_service.ingest(_recording(owner.id, minutes=0, source=_file("b" * 64)), db)
        elsewhere = ingestion_service.ingest(
            _recording(owner.id, start=DEFAULT_START + timedelta(minutes=10), minutes=0, source=_file("c" * 64)), db
        )

        assert (same.outcome, same.activity.id) == (_Outcome.ATTACHED, stored.id)
        assert elsewhere.outcome is _Outcome.CREATED

    def test_a_sport_that_cannot_be_the_same_effort_is_a_new_activity(self, db, owner):
        _stored_with_file(db, owner, sport=_Type.RUN)

        result = ingestion_service.ingest(_recording(owner.id, sport=_Type.LAP_SWIMMING, source=_file("b" * 64)), db)

        assert result.outcome is _Outcome.CREATED

    @pytest.mark.parametrize(
        ("stored", "incoming"),
        [
            (_Type.RUN, _Type.TRAIL_RUN),
            (_Type.RIDE, _Type.GRAVEL_RIDE),
            (_Type.RUN, _Type.VIRTUAL_RUN),
            (_Type.LAP_SWIMMING, _Type.OPEN_WATER_SWIMMING),
        ],
    )
    def test_two_types_of_one_sport_are_the_same_effort(self, db, owner, stored, incoming):
        recorded = _stored_with_file(db, owner, sport=stored)

        result = ingestion_service.ingest(_recording(owner.id, sport=incoming, source=_file("b" * 64)), db)

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, recorded.id)

    def test_a_type_that_is_no_sports_matches_only_itself(self, db, owner):
        _stored_with_file(db, owner, sport=_Type.YOGA)

        other = ingestion_service.ingest(_recording(owner.id, sport=_Type.WORKOUT, source=_file("b" * 64)), db)
        same = ingestion_service.ingest(_recording(owner.id, sport=_Type.YOGA, source=_file("c" * 64)), db)

        assert other.outcome is _Outcome.CREATED
        assert same.outcome is _Outcome.ATTACHED

    def test_a_multisport_activity_matches_any_type(self, db, owner):
        recorded = _stored_with_file(db, owner, sport=_Type.RIDE)

        result = ingestion_service.ingest(_recording(owner.id, sport=_Type.MULTISPORT, source=_file("b" * 64)), db)

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, recorded.id)

    def test_the_greatest_overlap_wins(self, db, owner):
        earlier = make_activity_at(db, owner.id, DEFAULT_START, activity_type=_Type.RUN.stored)
        later = make_activity_at(db, owner.id, DEFAULT_START + timedelta(minutes=5), activity_type=_Type.RUN.stored)

        result = ingestion_service.ingest(
            _recording(owner.id, start=DEFAULT_START + timedelta(minutes=3), source=_file("3" * 64)), db
        )

        assert result.activity.id == later.id
        assert earlier.id != later.id

    def test_another_users_activity_is_not_the_effort(self, db, owner):
        other = make_user(db, timezone="UTC")
        _stored_with_file(db, other)

        assert ingestion_service.ingest(_recording(owner.id, source=_file("b" * 64)), db).outcome is _Outcome.CREATED

    def test_an_activity_that_started_over_a_week_earlier_is_out_of_reach(self, db, owner):
        make_activity_at(
            db, owner.id, DEFAULT_START - timedelta(days=8), duration=timedelta(days=9), activity_type=_Type.RUN.stored
        )

        assert ingestion_service.ingest(_recording(owner.id, source=_file("b" * 64)), db).outcome is _Outcome.CREATED

    def test_a_leg_is_never_a_candidate_its_parent_stands_for_it(self, db, owner):
        parent, legs = make_multisport(db, owner.id, start=DEFAULT_START)

        candidates = activity_crud.list_effort_candidates(
            owner.id, DEFAULT_START, DEFAULT_START + timedelta(hours=1), timedelta(days=7), db
        )

        assert [candidate.id for candidate in candidates] == [parent.id]
        assert legs


class TestWhatAMatchDoes:
    def test_the_exact_source_is_found_before_any_effort(self, db, owner):
        stored = _stored_with_file(db, owner, content_hash="1" * 64)
        make_activity_at(db, owner.id, DEFAULT_START + timedelta(minutes=1), activity_type=_Type.RUN.stored)

        result = ingestion_service.ingest(_recording(owner.id, source=_file("1" * 64)), db)

        assert (result.outcome, result.activity.id) == (_Outcome.EXISTING, stored.id)

    def test_a_source_of_the_same_effort_is_attached_and_the_activity_keeps_its_data(self, db, owner, published):
        stored = _stored_with_file(db, owner, name="Mine", distance=5000)
        db.commit()
        published[activity_events.ACTIVITY_CREATED].clear()

        result = ingestion_service.ingest(
            _recording(owner.id, name="Theirs", distance=9999, source=_file("b" * 64, precedence=1)), db
        )
        db.commit()

        assert result.outcome is _Outcome.ATTACHED
        row = activity_crud.get_activity_by_id(stored.id, db)
        assert (row.name, row.distance, row.version) == ("Mine", 5000, 1)
        assert _sources_of(db, stored.id) == [("file", 1), ("file", 2)]
        assert published[activity_events.ACTIVITY_CREATED] == []
        assert len(db.scalars(select(activity_models.Activity.id)).all()) == 1

    def test_the_attached_source_makes_the_next_import_of_it_a_no_op(self, db, owner):
        stored = _stored_with_file(db, owner)
        ingestion_service.ingest(_recording(owner.id, source=_file("b" * 64, precedence=1)), db)

        again = ingestion_service.ingest(_recording(owner.id, source=_file("b" * 64, precedence=1)), db)

        assert (again.outcome, again.activity.id) == (_Outcome.EXISTING, stored.id)

    def test_a_recording_with_no_source_of_an_effort_the_owner_has_adds_nothing(self, db, owner):
        stored = _stored_with_file(db, owner)

        result = ingestion_service.ingest(_recording(owner.id), db)

        assert (result.outcome, result.activity.id) == (_Outcome.EXISTING, stored.id)
        assert _sources_of(db, stored.id) == [("file", 2)]

    def test_a_better_source_asks_for_a_recompute_when_the_caller_can_do_one(self, db, owner):
        stored = _stored_with_file(db, owner, precedence=1)

        result = ingestion_service.ingest(
            _recording(owner.id, source=_file("b" * 64, precedence=2)), db, allow_recompute=True
        )

        assert (result.outcome, result.activity.id) == (_Outcome.BETTER_SOURCE, stored.id)
        assert result.best_precedence == 1
        assert _sources_of(db, stored.id) == [("file", 1)], "nothing is staged"

    def test_a_better_source_is_attached_when_the_caller_cannot_recompute(self, db, owner):
        stored = _stored_with_file(db, owner, precedence=1)

        result = ingestion_service.ingest(_recording(owner.id, source=_file("b" * 64, precedence=2)), db)

        assert result.outcome is _Outcome.ATTACHED
        assert _sources_of(db, stored.id) == [("file", 1), ("file", 2)]

    def test_a_source_that_ties_is_attached_and_the_stored_recording_kept(self, db, owner):
        _stored_with_file(db, owner, precedence=2)

        result = ingestion_service.ingest(
            _recording(owner.id, source=_file("b" * 64, precedence=2)), db, allow_recompute=True
        )

        assert result.outcome is _Outcome.ATTACHED

    def test_a_worse_source_is_attached(self, db, owner):
        _stored_with_file(db, owner, precedence=2)

        result = ingestion_service.ingest(
            _recording(owner.id, source=_file("b" * 64, precedence=1)), db, allow_recompute=True
        )

        assert result.outcome is _Outcome.ATTACHED

    def test_an_activity_none_of_whose_sources_is_known_is_never_replaced(self, db, owner):
        make_activity_at(db, owner.id, DEFAULT_START, activity_type=_Type.RUN.stored)

        result = ingestion_service.ingest(
            _recording(owner.id, source=_file("b" * 64, precedence=2)), db, allow_recompute=True
        )

        assert result.outcome is _Outcome.ATTACHED

    def test_a_better_multisport_source_is_attached_to_a_single_activity_not_recomputed(self, db, owner):
        stored = _stored_with_file(db, owner, precedence=0, sport=_Type.RUN)

        result = ingestion_service.ingest_group(
            _recording(owner.id, sport=_Type.MULTISPORT, source=_file("b" * 64, precedence=2)),
            [_recording(owner.id, sport=_Type.RUN, source=_file("b" * 64, precedence=2))],
            db,
            allow_recompute=True,
        )

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, stored.id)

    def test_a_better_single_source_is_attached_to_a_multisport_activity_not_recomputed(self, db, owner):
        parent, _legs = make_multisport(db, owner.id, start=DEFAULT_START)
        make_source(db, parent, kind="strava", provider_id=5, precedence=0)

        result = ingestion_service.ingest(
            _recording(owner.id, sport=_Type.RUN, source=_file("b" * 64, precedence=2)), db, allow_recompute=True
        )

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, parent.id)

    def test_a_group_of_the_same_effort_is_attached_by_its_parents_source(self, db, owner):
        parent, legs = make_multisport(db, owner.id, start=DEFAULT_START)
        make_source(db, parent, kind="file", file_sha256="1" * 64)

        result = ingestion_service.ingest_group(
            _recording(owner.id, sport=_Type.MULTISPORT, minutes=200, source=_file("b" * 64)),
            [_recording(owner.id, sport=_Type.RUN, source=_file("b" * 64))],
            db,
        )

        assert (result.outcome, result.activity.id) == (_Outcome.ATTACHED, parent.id)
        assert len(db.scalars(select(activity_models.Activity.id)).all()) == len(legs) + 1

    def test_a_source_no_activity_carries_the_owners_ids_in_the_read_back(self, db, owner):
        stored = _stored_with_file(db, owner)

        ingestion_service.ingest(_recording(owner.id, strava_activity_id=77), db)

        assert activity_crud.get_activity_by_id(stored.id, db).strava_activity_id == 77


class TestTheMatchingLock:
    def test_an_ingest_waits_for_the_lock_an_import_of_the_same_user_holds(self, committed_sessions, arrange):
        user = arrange(lambda db: make_user(db, timezone="UTC"))
        with committed_sessions() as holder:
            activity_source_crud.lock_user_matching(user.id, holder)

            def ingest() -> uuid.UUID:
                with committed_sessions() as db:
                    result = ingestion_service.ingest(_recording(user.id, source=_file("a" * 64)), db)
                    db.commit()
                    return result.activity.id

            worker = concurrency.Worker(ingest)
            concurrency.wait_until_a_session_waits_for_a_lock(committed_sessions)
            assert worker.done is False
            holder.commit()
            worker.join()

        assert worker.error is None

    def test_another_users_ingest_does_not_wait(self, committed_sessions, arrange):
        user, other = (
            arrange(lambda db: make_user(db, timezone="UTC")),
            arrange(lambda db: make_user(db, timezone="UTC")),
        )
        with committed_sessions() as holder:
            activity_source_crud.lock_user_matching(user.id, holder)

            with committed_sessions() as db:
                result = ingestion_service.ingest(_recording(other.id, source=_file("a" * 64)), db)
                db.commit()

            assert result.outcome is _Outcome.CREATED

    def test_recordings_of_one_effort_ingested_at_once_make_one_activity_with_every_source(
        self, committed_sessions, arrange
    ):
        user = arrange(lambda db: make_user(db, timezone="UTC"))
        sources = [_file(str(n) * 64, precedence=2) for n in range(3)]
        barrier = threading.Barrier(len(sources))

        def ingest(source):
            def run():
                barrier.wait()
                with committed_sessions() as db:
                    result = ingestion_service.ingest(_recording(user.id, source=source), db)
                    db.commit()
                    return result.outcome

            return run

        workers = [concurrency.Worker(ingest(source)) for source in sources]
        for worker in workers:
            worker.join()

        assert [worker.error for worker in workers] == [None] * 3
        assert sorted(worker.result for worker in workers) == [_Outcome.ATTACHED, _Outcome.ATTACHED, _Outcome.CREATED]
        with committed_sessions() as db:
            assert len(db.scalars(select(activity_models.Activity.id)).all()) == 1
            assert len(db.scalars(select(activity_models.ActivitySource.id)).all()) == 3
