"""Persistence-level tests for ``create_activity`` against a real session.

The rest of ``test_crud.py`` mocks the ORM boundary, which is right for the query
shapes but cannot catch the failure this file exists for: the write contract and
the read model diverged, and ``create_activity`` was still writing the generated
id back onto its *input*. Every mocked test passed while every real import — the
Garmin sync, direct uploads and bulk import alike — died at the point of
persistence with::

    ValueError: "ActivityCore" object has no field "id"

So these exercise the actual schema objects and a real session.
"""

import pytest
from tests._helpers.db import create_sqlite_session

import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.schema as activities_schema


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()
    session.bind.dispose()


#: Privacy flags the enrichment step always sets before an activity reaches CRUD.
_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)


def _core(**overrides) -> activities_contracts.ActivityCore:
    """Build the ingestion contract exactly as a parser/provider adapter does.

    The ``hide_*`` flags and the elapsed/timer times are NOT NULL on the table;
    in production the ingestion pipeline's enrichment step fills the privacy
    flags from the owner's settings before persistence, so they are always
    present by the time CRUD sees the activity.
    """
    data = {
        "user_id": 1,
        "name": "Garmin ride",
        "distance": 42000,
        "activity_type": 1,
        # Parsers emit naive UTC wall-clock strings; the contract normalises them.
        "start_time": "2026-07-28T09:00:00",
        "end_time": "2026-07-28T10:00:00",
        "timezone": "Europe/Lisbon",
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3540.0,
        "visibility": 2,
        **{flag: False for flag in _PRIVACY_FLAGS},
    }
    data.update(overrides)
    return activities_contracts.ActivityCore(**data)


class TestCreateActivityReturnsTheReadModel:
    def test_returns_a_read_activity_with_the_generated_id(self, db):
        created = activities_crud.create_activity(
            _core(garminconnect_activity_id=23749427619),
            db,
            dedup_key="garmin:23749427619:1",
        )

        # The declared ``ActivityCore -> Activity`` signature is now honoured: a
        # freshly serialized read schema, not the caller's input handed back.
        assert isinstance(created, activities_schema.Activity)
        assert created.id is not None
        assert created.created_at is not None
        assert created.garminconnect_activity_id == 23749427619

    def test_does_not_write_read_only_fields_back_onto_the_contract(self, db):
        """The regression guard for the Garmin import failure.

        ``id`` and ``map_thumbnail_path`` are server-owned and live only on the
        read model, so assigning them to an ``ActivityCore`` raises. Nothing may
        reintroduce that write-back.
        """
        activity = _core()

        activities_crud.create_activity(activity, db)

        assert not hasattr(activity, "id")
        assert not hasattr(activity, "map_thumbnail_path")

    def test_leaves_a_caller_supplied_created_at_intact(self, db):
        """A profile restore supplies ``created_at`` to preserve the original.

        It is on the shared base (unlike ``id``), so it must round-trip rather
        than be overwritten with the row's own timestamp.
        """
        activity = _core(created_at="2020-01-01T00:00:00")

        created = activities_crud.create_activity(activity, db)

        assert created.created_at.year == 2020
        assert activity.created_at.year == 2020


class TestDuplicateStartTime:
    def test_second_activity_with_the_same_start_is_hidden(self, db):
        first = activities_crud.create_activity(_core(), db)
        second = activities_crud.create_activity(_core(name="Same start"), db)

        assert first.is_hidden is False
        # The flag is what the caller forwards to the notification subscriber so
        # it raises the duplicate variant instead of "new activity".
        assert second.is_hidden is True

    def test_the_flag_lands_on_the_row_not_the_input(self, db):
        activities_crud.create_activity(_core(), db)
        duplicate = _core(name="Same start")

        created = activities_crud.create_activity(duplicate, db)

        assert created.is_hidden is True
        # The write contract is not mutated on the way through.
        assert duplicate.is_hidden is False
