"""Storing a parsed activity: its children, the dedup keys, the duplicate-start flag and what a failure leaves."""

import uuid
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.events as activity_events
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity.models as activity_models
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_laps.models as laps_models
from tests._factories.activities import DEFAULT_START, make_parsed_activity
from tests._factories.users import make_user

_LAP = {"start_time": DEFAULT_START, "total_distance": 1000.0}


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.fixture
def user(arrange):
    return arrange(lambda db: make_user(db, timezone="UTC"))


class TestStoring:
    def test_the_activity_and_its_components_are_stored_in_the_callers_transaction(self, db, published):
        owner = make_user(db)

        stored = ingestion_service.store_parsed_activity(
            make_parsed_activity(owner.id, components={"laps": [_LAP, _LAP], "sets": None}), db
        )

        row = db.get(activity_models.Activity, stored.id)
        assert (row.name, row.user_id) == ("Imported ride", owner.id)
        assert _count(db, laps_models.ActivityLaps) == 2
        assert published[activity_events.ACTIVITY_CREATED] == []

    def test_created_is_published_after_the_commit_with_the_source_and_the_owner(self, db, published):
        owner = make_user(db)

        stored = ingestion_service.store_parsed_activity(
            make_parsed_activity(owner.id, source=activity_contracts.ImportSource(kind="upload")), db
        )
        db.commit()

        [event] = published[activity_events.ACTIVITY_CREATED]
        assert event.payload["activity_id"] == str(stored.id)
        assert (event.payload["user_id"], event.payload["duplicate_start_time"]) == (str(owner.id), False)
        assert event.source == "ingest:upload"

    def test_an_activity_with_no_source_is_published_from_an_unknown_source(self, db, published):
        owner = make_user(db)

        ingestion_service.store_parsed_activity(make_parsed_activity(owner.id), db)
        db.commit()

        assert [e.source for e in published[activity_events.ACTIVITY_CREATED]] == ["ingest:unknown"]

    def test_a_second_activity_at_the_same_start_is_stored_hidden_and_published_as_a_duplicate(self, db, published):
        owner = make_user(db)
        ingestion_service.store_parsed_activity(make_parsed_activity(owner.id), db)

        duplicate = ingestion_service.store_parsed_activity(make_parsed_activity(owner.id, name="Again"), db)
        db.commit()

        assert duplicate.is_hidden is True
        flags = [e.payload["duplicate_start_time"] for e in published[activity_events.ACTIVITY_CREATED]]
        assert flags == [False, True]


class TestFailures:
    def test_an_unknown_component_fails_closed_before_anything_is_stored(self, user, committed_sessions, published):
        with committed_sessions() as db:
            with pytest.raises(core_exceptions.ProcessingError):
                ingestion_service.store_parsed_activity(
                    make_parsed_activity(user.id, components={"telemetry": [1]}), db
                )
            db.commit()

        with committed_sessions() as db:
            assert _count(db, activity_models.Activity) == 0
        assert published[activity_events.ACTIVITY_CREATED] == []

    def test_an_unknown_component_is_refused_even_when_the_activity_is_already_stored(self, user, committed_sessions):
        source = activity_contracts.ImportSource(kind="upload", dedup_key="k")
        with committed_sessions() as db:
            ingestion_service.store_parsed_activity(make_parsed_activity(user.id, source=source), db)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
            ingestion_service.store_parsed_activity(
                make_parsed_activity(user.id, source=source, components={"telemetry": [1]}), db
            )

    def test_rows_of_the_wrong_shape_for_a_component_propagate_and_leave_nothing_once_the_session_closes(
        self, user, committed_sessions, published
    ):
        with committed_sessions() as db, pytest.raises(ValidationError):
            ingestion_service.store_parsed_activity(make_parsed_activity(user.id, components={"laps": "not rows"}), db)

        with committed_sessions() as db:
            assert _count(db, activity_models.Activity) == 0
        assert published[activity_events.ACTIVITY_CREATED] == []

    def test_a_session_closed_without_committing_leaves_nothing_and_publishes_nothing(
        self, user, committed_sessions, published
    ):
        with committed_sessions() as db:
            ingestion_service.store_parsed_activity(make_parsed_activity(user.id, components={"laps": [_LAP]}), db)

        with committed_sessions() as db:
            assert (_count(db, activity_models.Activity), _count(db, laps_models.ActivityLaps)) == (0, 0)
        assert published[activity_events.ACTIVITY_CREATED] == []


class TestReimport:
    def test_an_explicit_dedup_key_makes_a_second_import_a_no_op_that_returns_the_first(
        self, user, committed_sessions, published
    ):
        source = activity_contracts.ImportSource(kind="upload", dedup_key="same-key")
        with committed_sessions() as db:
            first = ingestion_service.store_parsed_activity(make_parsed_activity(user.id, source=source), db)
            db.commit()
        with committed_sessions() as db:
            second = ingestion_service.store_parsed_activity(
                make_parsed_activity(user.id, source=source, components={"laps": [_LAP]}), db
            )
            db.commit()

        assert second.id == first.id
        with committed_sessions() as db:
            assert (_count(db, activity_models.Activity), _count(db, laps_models.ActivityLaps)) == (1, 0)
        assert len(published[activity_events.ACTIVITY_CREATED]) == 1

    def test_the_same_key_of_another_user_is_a_different_activity(self, user, arrange, committed_sessions):
        other = arrange(lambda db: make_user(db))
        source = activity_contracts.ImportSource(kind="upload", dedup_key="same-key")
        with committed_sessions() as db:
            first = ingestion_service.store_parsed_activity(make_parsed_activity(user.id, source=source), db)
            second = ingestion_service.store_parsed_activity(make_parsed_activity(other.id, source=source), db)
            db.commit()

        assert first.id != second.id

    @pytest.mark.parametrize(
        ("fields", "source", "expected"),
        [
            ({"strava_activity_id": 7, "garminconnect_activity_id": 8}, None, "strava:7"),
            ({"garminconnect_activity_id": 8}, None, f"garmin:8:{int(DEFAULT_START.timestamp())}"),
            (
                {},
                activity_contracts.ImportSource(kind="upload", content_hash="abc"),
                f"file:abc:{int(DEFAULT_START.timestamp())}",
            ),
            ({"strava_activity_id": 7}, activity_contracts.ImportSource(kind="upload", content_hash="abc"), "strava:7"),
            ({}, activity_contracts.ImportSource(kind="upload"), None),
            ({}, None, None),
        ],
    )
    def test_the_stored_dedup_key_is_the_provider_id_then_the_file_hash_salted_with_the_start(
        self, db, fields, source, expected
    ):
        owner = make_user(db)

        stored = ingestion_service.store_parsed_activity(make_parsed_activity(owner.id, source=source, **fields), db)

        row = db.get(activity_models.Activity, stored.id)
        assert row.dedup_key == expected

    def test_activities_of_one_garmin_file_stay_distinct_by_their_start(self, db):
        owner = make_user(db)
        first = ingestion_service.store_parsed_activity(make_parsed_activity(owner.id, garminconnect_activity_id=8), db)
        second = ingestion_service.store_parsed_activity(
            make_parsed_activity(owner.id, garminconnect_activity_id=8, start=DEFAULT_START + timedelta(hours=3)), db
        )
        again = ingestion_service.store_parsed_activity(make_parsed_activity(owner.id, garminconnect_activity_id=8), db)

        assert first.id != second.id
        assert again.id == first.id


class TestIntegrityFailures:
    """A constraint the dedup race does not explain is a processing failure, not a duplicate."""

    def test_an_owner_who_does_not_exist_with_no_dedup_key_is_a_processing_failure(self, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
            ingestion_service.store_parsed_activity(make_parsed_activity(uuid.uuid4()), db)

    def test_an_owner_who_does_not_exist_with_a_dedup_key_nobody_stored_is_a_processing_failure(
        self, committed_sessions
    ):
        source = activity_contracts.ImportSource(kind="upload", dedup_key="orphan")

        with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
            ingestion_service.store_parsed_activity(make_parsed_activity(uuid.uuid4(), source=source), db)

    def test_nothing_is_stored_by_a_failed_import(self, committed_sessions):
        with committed_sessions() as db, pytest.raises(core_exceptions.ProcessingError):
            ingestion_service.store_parsed_activity(make_parsed_activity(uuid.uuid4()), db)

        with committed_sessions() as db:
            assert _count(db, activity_models.Activity) == 0

    def test_a_garmin_activity_without_a_start_is_keyed_by_its_id_alone(self):
        activity = activity_schema.ActivityBase.model_validate(
            {
                "distance": 1,
                "name": "n",
                "activity_type": 1,
                "start_time": None,
                "garminconnect_activity_id": 8,
            }
        )

        assert ingestion_service._derive_dedup_key(activity, None) == "garmin:8"
