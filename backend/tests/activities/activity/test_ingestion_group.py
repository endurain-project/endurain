"""Storing a multisport group: the parent and its legs in one transaction, their keys, privacy and events."""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import func, select

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.events as activity_events
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.models as activity_models
import modules.activities.activity_laps.models as laps_models
from tests._factories.activities import DEFAULT_START, make_activity_at, make_parsed_activity
from tests._factories.users import make_user

_Type = activity_constants.ActivityType
_LEG_TYPES = (_Type.RUN, _Type.RIDE, _Type.RUN)
_LAP = {"start_time": DEFAULT_START, "total_distance": 1000.0}


def _group(user_id, *, hash_="abc", parent_fields=None, leg_fields=None):
    """The parsed parent and legs of a file of three 20-minute legs, as the pipeline hands them over."""
    source = activity_contracts.ImportSource(kind="upload", content_hash=hash_)
    legs = [
        make_parsed_activity(
            user_id,
            source=source,
            start=DEFAULT_START + timedelta(minutes=20 * index),
            end_time=DEFAULT_START + timedelta(minutes=20 * (index + 1)),
            activity_type=leg_type.stored,
            name=leg_type.label,
            components={"laps": [_LAP]},
            **(leg_fields or {}),
        )
        for index, leg_type in enumerate(_LEG_TYPES)
    ]
    parent = make_parsed_activity(
        user_id,
        source=source,
        end_time=DEFAULT_START + timedelta(hours=1),
        activity_type=_Type.MULTISPORT.stored,
        name="Triathlon",
        components={"streams": [], "laps": []},
        **(parent_fields or {}),
    )
    return parent, legs


def _rows(db):
    return list(db.scalars(select(activity_models.Activity).order_by(activity_models.Activity.start_time)))


def _group_rows(db):
    return [row for row in _rows(db) if row.dedup_key and row.dedup_key.startswith("file:abc")]


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


class TestStoringAGroup:
    def test_the_parent_and_its_legs_are_stored_and_the_parent_is_returned(self, db, owner):
        parent, legs = _group(owner.id)

        stored = ingestion_service.store_parsed_group(parent, legs, db)

        [top] = stored
        rows = {row.id: row for row in _rows(db)}
        assert len(rows) == 4
        assert rows[top.id].activity_type == _Type.MULTISPORT.stored
        assert rows[top.id].parent_activity_id is None
        leg_rows = [row for row in rows.values() if row.id != top.id]
        assert {row.parent_activity_id for row in leg_rows} == {top.id}
        assert db.scalar(select(func.count()).select_from(laps_models.ActivityLaps)) == 3

    def test_a_session_closed_without_committing_leaves_nothing(self, committed_sessions, arrange):
        user = arrange(lambda db: make_user(db, timezone="UTC"))
        with committed_sessions() as db:
            parent, legs = _group(user.id)
            ingestion_service.store_parsed_group(parent, legs, db)

        with committed_sessions() as db:
            assert _rows(db) == []

    def test_the_parent_is_keyed_by_the_bare_file_hash_and_the_legs_by_hash_and_start(self, db, owner):
        parent, legs = _group(owner.id)

        ingestion_service.store_parsed_group(parent, legs, db)

        keys = [row.dedup_key for row in _rows(db)]
        starts = [int((DEFAULT_START + timedelta(minutes=20 * index)).timestamp()) for index in range(3)]
        assert sorted(keys) == sorted(["file:abc", *(f"file:abc:{start}" for start in starts)])
        assert next(row for row in _rows(db) if row.parent_activity_id is None).dedup_key == "file:abc"

    def test_a_garmin_group_is_keyed_by_the_bare_garmin_id_on_the_parent(self, db, owner):
        parent, legs = _group(owner.id, hash_=None, parent_fields={"garminconnect_activity_id": 77})
        for leg in legs:
            leg.activity.garminconnect_activity_id = 77

        ingestion_service.store_parsed_group(parent, legs, db)

        top = next(row for row in _rows(db) if row.parent_activity_id is None)
        assert top.dedup_key == "garmin:77"
        assert {row.dedup_key for row in _rows(db) if row.id != top.id} == {
            f"garmin:77:{int((DEFAULT_START + timedelta(minutes=20 * index)).timestamp())}" for index in range(3)
        }

    def test_the_legs_take_the_privacy_of_the_parent(self, db, owner):
        parent, legs = _group(owner.id, parent_fields={"visibility": 2, "hide_hr": True, "hide_map": True})

        ingestion_service.store_parsed_group(parent, legs, db)

        for row in _rows(db):
            assert (row.visibility, row.hide_hr, row.hide_map, row.hide_power) == (2, True, True, False)

    def test_the_callers_leg_objects_are_left_as_they_were(self, db, owner):
        parent, legs = _group(owner.id, parent_fields={"hide_hr": True})

        ingestion_service.store_parsed_group(parent, legs, db)

        assert [leg.activity.hide_hr for leg in legs] == [False, False, False]


class TestSameStart:
    def test_the_parent_alone_is_checked_and_the_legs_take_its_hidden_flag(self, db, owner):
        make_activity_at(db, owner.id, DEFAULT_START)
        make_activity_at(db, owner.id, DEFAULT_START + timedelta(minutes=20))
        parent, legs = _group(owner.id)

        ingestion_service.store_parsed_group(parent, legs, db)

        group = _group_rows(db)
        assert len(group) == 4
        assert all(row.is_hidden for row in group)

    def test_a_group_with_no_look_alike_has_nothing_hidden(self, db, owner):
        make_activity_at(db, owner.id, DEFAULT_START + timedelta(minutes=20), name="elsewhere")
        parent, legs = _group(owner.id)

        ingestion_service.store_parsed_group(parent, legs, db)

        assert [row.is_hidden for row in _group_rows(db)] == [False] * 4


class TestEvents:
    def test_created_is_published_for_the_parent_and_each_leg_with_the_parent_named_on_the_legs(
        self, db, owner, published
    ):
        parent, legs = _group(owner.id)

        [top] = ingestion_service.store_parsed_group(parent, legs, db)
        db.commit()

        events = published[activity_events.ACTIVITY_CREATED]
        assert len(events) == 4
        by_parent = [event.payload["parent_activity_id"] for event in events]
        assert by_parent.count(None) == 1
        assert by_parent.count(str(top.id)) == 3
        assert next(e for e in events if e.payload["parent_activity_id"] is None).payload["activity_id"] == str(top.id)
        assert {event.source for event in events} == {"ingest:upload"}

    def test_a_stand_alone_activity_is_published_without_a_parent(self, db, owner, published):
        ingestion_service.store_parsed_activity(make_parsed_activity(owner.id), db)
        db.commit()

        [event] = published[activity_events.ACTIVITY_CREATED]
        assert event.payload["parent_activity_id"] is None

    def test_a_duplicate_start_is_flagged_on_the_parents_event_only(self, db, owner, published):
        make_activity_at(db, owner.id, DEFAULT_START)
        parent, legs = _group(owner.id)

        ingestion_service.store_parsed_group(parent, legs, db)
        db.commit()

        events = published[activity_events.ACTIVITY_CREATED]
        flagged = [event.payload["parent_activity_id"] for event in events if event.payload["duplicate_start_time"]]
        assert flagged == [None]


class TestReimport:
    def test_a_second_import_returns_the_stored_parent_and_stages_nothing(self, db, owner, published):
        parent, legs = _group(owner.id)
        [first] = ingestion_service.store_parsed_group(parent, legs, db)
        db.commit()

        again_parent, again_legs = _group(owner.id)
        [second] = ingestion_service.store_parsed_group(again_parent, again_legs, db)
        db.commit()

        assert second.id == first.id
        assert len(_rows(db)) == 4
        assert len(published[activity_events.ACTIVITY_CREATED]) == 4

    def test_a_file_stored_leg_by_leg_before_grouping_existed_returns_those_legs_and_stores_nothing(
        self, db, owner, published
    ):
        _parent, legs = _group(owner.id)
        old = [ingestion_service.store_parsed_activity(leg, db) for leg in legs]
        db.commit()
        parent, legs = _group(owner.id)

        stored = ingestion_service.store_parsed_group(parent, legs, db)
        db.commit()

        assert [activity.id for activity in stored] == [activity.id for activity in old]
        assert len(_rows(db)) == 3
        assert all(row.parent_activity_id is None for row in _rows(db))
        assert len(published[activity_events.ACTIVITY_CREATED]) == 3

    def test_one_leg_stored_before_grouping_is_enough_to_keep_the_file_ungrouped(self, db, owner):
        _parent, legs = _group(owner.id)
        old = ingestion_service.store_parsed_activity(legs[1], db)
        parent, legs = _group(owner.id)

        stored = ingestion_service.store_parsed_group(parent, legs, db)

        assert [activity.id for activity in stored] == [old.id]
        assert len(_rows(db)) == 1


class TestALoserOfTheRace:
    def test_that_finds_the_winners_legs_returns_the_winners_parent_not_its_legs(self, db, owner, monkeypatch):
        parent, legs = _group(owner.id)
        [winner] = ingestion_service.store_parsed_group(parent, legs, db)
        db.commit()
        # The other import looked for the parent before the winner committed, and for the legs after.
        lookup = ingestion_service.activity_crud.get_activity_by_dedup_key
        missed: list[str] = []

        def parent_not_yet_committed(dedup_key, user_id, session):
            if dedup_key == "file:abc" and not missed:
                missed.append(dedup_key)
                return None
            return lookup(dedup_key, user_id, session)

        monkeypatch.setattr(ingestion_service.activity_crud, "get_activity_by_dedup_key", parent_not_yet_committed)
        parent, legs = _group(owner.id)

        stored = ingestion_service.store_parsed_group(parent, legs, db)

        assert [activity.id for activity in stored] == [winner.id]
        assert len(_group_rows(db)) == 4


class TestRace:
    def test_concurrent_imports_of_one_group_store_it_once_and_every_loser_returns_the_winner(
        self, committed_sessions, arrange
    ):
        user = arrange(lambda db: make_user(db, timezone="UTC"))
        barrier = threading.Barrier(4)
        results: list[object] = []
        errors: list[BaseException] = []

        def import_it():
            try:
                barrier.wait()
                with committed_sessions() as db:
                    parent, legs = _group(user.id)
                    [top] = ingestion_service.store_parsed_group(parent, legs, db)
                    db.commit()
                    results.append(top.id)
            except BaseException as err:
                errors.append(err)

        threads = [threading.Thread(target=import_it) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(set(results)) == 1
        with committed_sessions() as db:
            assert len(_rows(db)) == 4
