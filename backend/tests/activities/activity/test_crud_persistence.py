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

from datetime import UTC, datetime, timedelta

import pytest
from tests._helpers.db import create_sqlite_session

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema


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


def _core(**overrides) -> activity_contracts.ActivityCore:
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
    return activity_contracts.ActivityCore(**data)


class TestCreateActivityReturnsTheReadModel:
    def test_returns_a_read_activity_with_the_generated_id(self, db):
        created = activity_crud.create_activity(
            _core(garminconnect_activity_id=23749427619),
            db,
            dedup_key="garmin:23749427619:1",
        )

        # The declared ``ActivityCore -> Activity`` signature is now honoured: a
        # freshly serialized read schema, not the caller's input handed back.
        assert isinstance(created, activity_schema.ActivityRead)
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

        activity_crud.create_activity(activity, db)

        assert not hasattr(activity, "id")
        assert not hasattr(activity, "map_thumbnail_path")

    def test_leaves_a_caller_supplied_created_at_intact(self, db):
        """A profile restore supplies ``created_at`` to preserve the original.

        It is on the shared base (unlike ``id``), so it must round-trip rather
        than be overwritten with the row's own timestamp.
        """
        activity = _core(created_at="2020-01-01T00:00:00")

        created = activity_crud.create_activity(activity, db)

        assert created.created_at.year == 2020
        assert activity.created_at.year == 2020


class TestDuplicateStartTime:
    def test_second_activity_with_the_same_start_is_hidden(self, db):
        first = activity_crud.create_activity(_core(), db)
        second = activity_crud.create_activity(_core(name="Same start"), db)

        assert first.is_hidden is False
        # The flag is what the caller forwards to the notification subscriber so
        # it raises the duplicate variant instead of "new activity".
        assert second.is_hidden is True

    def test_the_flag_lands_on_the_row_not_the_input(self, db):
        activity_crud.create_activity(_core(), db)
        duplicate = _core(name="Same start")

        created = activity_crud.create_activity(duplicate, db)

        assert created.is_hidden is True
        # The write contract is not mutated on the way through.
        assert duplicate.is_hidden is False

    def test_a_third_activity_with_the_same_start_is_still_imported(self, db):
        """Duplicates are stored hidden, so the lookup sees several matching rows.

        ``scalar_one_or_none`` raised ``MultipleResultsFound`` on the third import,
        failing it with a 500 instead of storing another hidden duplicate.
        """
        activity_crud.create_activity(_core(), db)
        activity_crud.create_activity(_core(name="Second"), db)

        third = activity_crud.create_activity(_core(name="Third"), db)

        assert third.is_hidden is True
        assert third.id is not None


class TestLocationLookupSchedule:
    """The backfill's candidate query, which only a real database can evaluate."""

    _NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    def _ids(self, db, **kwargs):
        return [ref.id for ref in activity_crud.get_activities_missing_location(db, due_at=self._NOW, **kwargs)]

    def test_lists_unresolved_activities_never_deferred(self, db):
        created = activity_crud.create_activity(_core(), db)

        assert self._ids(db) == [created.id]

    def test_an_activity_with_a_location_is_not_a_candidate(self, db):
        created = activity_crud.create_activity(_core(), db)
        activity_crud.update_activity_location(created.id, "Lisbon", None, "Portugal", db)

        assert self._ids(db) == []

    def test_a_deferred_activity_is_skipped_until_it_is_due(self, db):
        later = activity_crud.create_activity(_core(), db)
        earlier = activity_crud.create_activity(_core(start_time="2026-07-29T09:00:00"), db)
        activity_crud.defer_location_lookups([later.id], self._NOW + timedelta(hours=1), db)
        activity_crud.defer_location_lookups([earlier.id], self._NOW - timedelta(hours=1), db)

        assert self._ids(db) == [earlier.id]

    def test_pages_after_the_given_id(self, db):
        first = activity_crud.create_activity(_core(), db)
        second = activity_crud.create_activity(_core(start_time="2026-07-29T09:00:00"), db)

        assert self._ids(db, after_id=first.id) == [second.id]


class TestThumbnailAttemptSchedule:
    """The thumbnail backfill's candidate query, which only a real database can evaluate."""

    _NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    def _ids(self, db):
        return [ref.id for ref in activity_crud.get_activities_without_thumbnail(db, due_at=self._NOW)]

    def test_an_activity_with_no_thumbnail_is_a_candidate(self, db):
        created = activity_crud.create_activity(_core(), db)

        assert self._ids(db) == [created.id]

    def test_a_deferred_activity_is_skipped_until_it_is_due(self, db):
        later = activity_crud.create_activity(_core(), db)
        earlier = activity_crud.create_activity(_core(start_time="2026-07-29T09:00:00"), db)
        activity_crud.defer_thumbnail_attempts([later.id], self._NOW + timedelta(hours=1), db)
        activity_crud.defer_thumbnail_attempts([earlier.id], self._NOW - timedelta(hours=1), db)

        assert self._ids(db) == [earlier.id]

    def test_an_activity_with_a_thumbnail_is_not_a_candidate(self, db):
        created = activity_crud.create_activity(_core(), db)
        activity_crud.set_activity_thumbnail_key(created.id, f"{created.id}.webp", db)

        assert self._ids(db) == []

    def test_clearing_every_key_also_clears_the_deferral(self, db):
        """Regenerating after a tile-server change must retry what failed under the old one."""
        created = activity_crud.create_activity(_core(), db)
        activity_crud.defer_thumbnail_attempts([created.id], self._NOW + timedelta(days=1), db)

        activity_crud.clear_all_activity_thumbnail_keys(db)

        assert self._ids(db) == [created.id]
