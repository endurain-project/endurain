"""The activity sources in a profile archive: written on export, restored on import, derived for an older archive."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jasil.providers as platform_providers
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
from tests._factories.activities import DEFAULT_START, make_activity, make_activity_at, make_source
from tests._factories.users import make_user
from tests.activities.activity_profile_transfer import support

_SHA = "d" * 64
_PATH = "data/activity_sources.json"
_ARCHIVED = uuid.UUID("00000000-0000-4000-8000-00000000b001")
_ARCHIVED_LEG = uuid.UUID("00000000-0000-4000-8000-00000000b002")
_PRIVACY_FLAGS = tuple(
    f"hide_{name}"
    for name in (
        "start_time",
        "location",
        "map",
        "hr",
        "power",
        "cadence",
        "elevation",
        "speed",
        "pace",
        "laps",
        "workout_sets_steps",
        "gear",
    )
)


@pytest.fixture
def storage(_publish_local_platform) -> platform_providers.StorageProvider:
    return _publish_local_platform.storage


def _row(activity_id: uuid.UUID = _ARCHIVED, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": str(activity_id),
        "distance": 1000,
        "name": "Morning Run",
        "activity_type": 1,
        "start_time": "2024-01-01T08:00:00",
        "end_time": "2024-01-01T09:00:00",
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3500.0,
        "is_hidden": False,
        **{flag: False for flag in _PRIVACY_FLAGS},
    }
    row.update(overrides)
    return row


def _sources_of(db: Session, user_id: uuid.UUID) -> list[tuple]:
    """Every source of a user as ``(activity name, kind, provider id, file hash, start, precedence)``."""
    rows = db.execute(
        select(
            activity_models.Activity.name,
            activity_models.ActivitySource.kind,
            activity_models.ActivitySource.provider_id,
            activity_models.ActivitySource.file_sha256,
            activity_models.ActivitySource.session_start,
            activity_models.ActivitySource.precedence,
        )
        .join(activity_models.Activity, activity_models.Activity.id == activity_models.ActivitySource.activity_id)
        .where(activity_models.ActivitySource.user_id == user_id)
    ).all()
    return sorted(tuple(row) for row in rows)


class TestExport:
    def test_the_archive_lists_each_source_under_its_activity_and_counts_them(self, db: Session, storage) -> None:
        user = make_user(db)
        merged = make_activity(db, user.id, name="merged", strava_activity_id=7)
        make_source(db, merged, kind="file", file_sha256=_SHA, session_start=DEFAULT_START)
        make_activity_at(db, user.id, DEFAULT_START + timedelta(days=1), name="plain")
        other = make_user(db)
        make_activity(db, other.id, name="theirs", garminconnect_activity_id=9)

        exported = support.export_activities(db, user.id, storage)

        records = exported.json(_PATH)
        assert sorted((r["activity_id"] == str(merged.id), r["kind"]) for r in records) == [
            (True, "file"),
            (True, "strava"),
        ]
        by_kind = {r["kind"]: r for r in records}
        assert (
            by_kind["strava"]["provider_id"],
            by_kind["strava"]["session_start"],
            by_kind["strava"]["precedence"],
        ) == (
            7,
            None,
            0,
        )
        assert (by_kind["file"]["file_sha256"], by_kind["file"]["precedence"]) == (_SHA, 2)
        assert exported.counts["activity_sources"] == 2

    def test_a_user_without_sources_gets_an_empty_entry_and_a_zero_count(self, db: Session, storage) -> None:
        user = make_user(db)
        make_activity(db, user.id)

        exported = support.export_activities(db, user.id, storage)

        assert exported.json(_PATH) == []
        assert exported.counts["activity_sources"] == 0


class TestImport:
    def test_an_export_restores_the_same_sources_under_the_new_activities(self, db: Session, storage) -> None:
        source_user = make_user(db)
        merged = make_activity(db, source_user.id, name="merged", strava_activity_id=7, garminconnect_activity_id=8)
        make_source(db, merged, kind="file", file_sha256=_SHA, session_start=DEFAULT_START)
        entries = support.export_activities(db, source_user.id, storage).entries
        target = make_user(db)

        restored = support.import_activities(db, target.id, storage, entries)

        assert _sources_of(db, target.id) == _sources_of(db, source_user.id)
        assert restored.counts["activity_sources"] == 3

    def test_the_restored_activity_reads_its_provider_ids_from_the_restored_sources(self, db: Session, storage) -> None:
        source_user = make_user(db)
        make_activity(db, source_user.id, strava_activity_id=7, garminconnect_activity_id=8)
        entries = support.export_activities(db, source_user.id, storage).entries
        target = make_user(db)

        support.import_activities(db, target.id, storage, entries)

        [activity] = activity_integration.list_user_activities_page(target.id, db, page_number=1, num_records=10)
        assert (activity.strava_activity_id, activity.garminconnect_activity_id) == (7, 8)


class TestAnOlderArchive:
    def test_the_provider_ids_of_an_activity_become_its_sources(self, db: Session, storage) -> None:
        target = make_user(db)
        entries = {
            "data/activities.json": [_row(name="old", strava_activity_id=7, garminconnect_activity_id=8)],
        }

        restored = support.import_activities(db, target.id, storage, entries)

        assert _sources_of(db, target.id) == [
            ("old", "garmin", 8, None, None, activity_constants.SOURCE_PRECEDENCE_DEVICE_FILE),
            ("old", "strava", 7, None, None, activity_constants.SOURCE_PRECEDENCE_API),
        ]
        assert restored.counts["activity_sources"] == 2

    def test_a_leg_takes_its_provider_id_with_its_own_start_and_its_parent_the_bare_id(
        self, db: Session, storage
    ) -> None:
        target = make_user(db)
        entries = {
            "data/activities.json": [
                _row(
                    name="parent",
                    garminconnect_activity_id=8,
                    activity_type=activity_constants.ActivityType.MULTISPORT.stored,
                ),
                _row(
                    _ARCHIVED_LEG,
                    name="leg",
                    garminconnect_activity_id=8,
                    parent_activity_id=str(_ARCHIVED),
                    start_time="2024-01-01T08:00:07.5",
                ),
            ],
        }

        support.import_activities(db, target.id, storage, entries)

        assert _sources_of(db, target.id) == [
            ("leg", "garmin", 8, None, datetime(2024, 1, 1, 8, 0, 7, tzinfo=UTC), 2),
            ("parent", "garmin", 8, None, None, 2),
        ]

    def test_an_activity_with_a_file_and_no_provider_id_takes_the_files_source(self, db: Session, storage) -> None:
        target = make_user(db)
        entries = {
            "data/activities.json": [_row(name="file")],
            f"activity_files/{_ARCHIVED}.gpx": support.GPX,
        }

        restored = support.import_activities(db, target.id, storage, entries)

        assert _sources_of(db, target.id) == [
            (
                "file",
                "file",
                None,
                hashlib.sha256(support.GPX).hexdigest(),
                datetime(2024, 1, 1, 8, 0, tzinfo=UTC),
                activity_constants.SOURCE_PRECEDENCE_GENERIC_FILE,
            )
        ]
        assert restored.counts["activity_files"] == 1

    def test_an_activity_with_a_provider_source_and_a_file_keeps_only_the_provider_source(
        self, db: Session, storage
    ) -> None:
        target = make_user(db)
        entries = {
            "data/activities.json": [_row(name="garmin", garminconnect_activity_id=8)],
            f"activity_files/{_ARCHIVED}.gpx": support.GPX,
        }

        support.import_activities(db, target.id, storage, entries)

        assert [(row[1], row[2]) for row in _sources_of(db, target.id)] == [("garmin", 8)]

    def test_an_archive_with_sources_derives_nothing_for_an_activity_it_lists_them_for(
        self, db: Session, storage
    ) -> None:
        target = make_user(db)
        entries = {
            "data/activities.json": [_row(name="a", strava_activity_id=7)],
            _PATH: [
                {
                    "activity_id": str(_ARCHIVED),
                    "kind": "strava",
                    "provider_id": 7,
                    "session_start": None,
                    "precedence": 0,
                }
            ],
        }

        restored = support.import_activities(db, target.id, storage, entries)

        assert _sources_of(db, target.id) == [("a", "strava", 7, None, None, 0)]
        assert restored.counts["activity_sources"] == 1

    def test_an_archive_written_before_the_unique_identity_restores_twice_without_failing(
        self, db: Session, storage
    ) -> None:
        target = make_user(db)
        entries = {"data/activities.json": [_row(name="old", strava_activity_id=7)]}

        support.import_activities(db, target.id, storage, entries)
        support.import_activities(db, target.id, storage, entries)

        assert len(_sources_of(db, target.id)) == 1


def _count(db: Session) -> int:
    return len(db.scalars(select(activity_models.Activity.id)).all())


class TestAnAccountThatAlreadyHasWhatTheArchiveHolds:
    def test_importing_the_same_archive_twice_creates_nothing_the_second_time(self, db: Session, storage) -> None:
        source_user = make_user(db)
        merged = make_activity(db, source_user.id, name="merged", strava_activity_id=7)
        make_source(db, merged, kind="file", file_sha256=_SHA, session_start=DEFAULT_START)
        make_activity_at(db, source_user.id, DEFAULT_START + timedelta(days=1), name="plain")
        entries = support.export_activities(db, source_user.id, storage).entries
        target = make_user(db)
        first = support.import_activities(db, target.id, storage, entries)
        rows = _count(db)
        sources = len(_sources_of(db, target.id))

        second = support.import_activities(db, target.id, storage, entries)

        assert (first.counts["activities"], first.counts["activities_skipped"]) == (2, 0)
        assert (second.counts["activities"], second.counts["activities_skipped"]) == (0, 2)
        assert second.counts["activity_sources"] == 0
        assert _count(db) == rows
        assert len(_sources_of(db, target.id)) == sources

    def test_an_activity_holding_a_source_the_account_has_is_skipped_with_its_components(
        self, db: Session, storage
    ) -> None:
        target = make_user(db)
        held = make_activity(
            db, target.id, name="held", strava_activity_id=7, start_time=DEFAULT_START + timedelta(days=9)
        )
        entries = {
            "data/activities.json": [_row(name="archived", strava_activity_id=7)],
            "data/activity_laps.json": [
                {"activity_id": str(_ARCHIVED), "start_time": "2024-01-01T08:00:00", "total_distance": 1000.0}
            ],
        }

        restored = support.import_activities(db, target.id, storage, entries)

        assert restored.counts["activities_skipped"] == 1
        assert restored.counts["activities"] == 0
        assert restored.counts["activity_laps"] == 0
        assert [
            a.id for a in activity_integration.list_user_activities_page(target.id, db, page_number=1, num_records=9)
        ] == [held.id]

    def test_an_activity_of_the_same_effort_as_one_the_account_has_is_skipped(self, db: Session, storage) -> None:
        target = make_user(db)
        make_activity(
            db,
            target.id,
            name="mine",
            start_time=datetime(2024, 1, 1, 8, 5, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 9, 5, tzinfo=UTC),
        )
        entries = {"data/activities.json": [_row(name="archived")]}

        restored = support.import_activities(db, target.id, storage, entries)

        assert (restored.counts["activities"], restored.counts["activities_skipped"]) == (0, 1)
        assert _count(db) == 1

    def test_an_activity_of_another_sport_at_the_same_time_is_restored(self, db: Session, storage) -> None:
        target = make_user(db)
        make_activity(
            db,
            target.id,
            start_time=datetime(2024, 1, 1, 8, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            activity_type=activity_constants.ActivityType.LAP_SWIMMING.stored,
        )

        restored = support.import_activities(db, target.id, storage, {"data/activities.json": [_row()]})

        assert (restored.counts["activities"], restored.counts["activities_skipped"]) == (1, 0)

    def test_the_legs_of_a_skipped_group_are_skipped_and_the_legs_of_a_restored_one_are_not(
        self, db: Session, storage
    ) -> None:
        target = make_user(db)
        multisport = activity_constants.ActivityType.MULTISPORT.stored
        make_activity(
            db,
            target.id,
            name="held group",
            start_time=datetime(2024, 1, 1, 8, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
            activity_type=multisport,
        )
        entries = {
            "data/activities.json": [
                _row(name="parent", activity_type=multisport),
                _row(_ARCHIVED_LEG, name="leg", parent_activity_id=str(_ARCHIVED)),
            ]
        }

        skipped = support.import_activities(db, target.id, storage, entries)
        far = {
            "data/activities.json": [
                _row(
                    name="parent",
                    activity_type=multisport,
                    start_time="2025-05-01T08:00:00",
                    end_time="2025-05-01T09:00:00",
                ),
                _row(
                    _ARCHIVED_LEG,
                    name="leg",
                    parent_activity_id=str(_ARCHIVED),
                    start_time="2025-05-01T08:00:00",
                    end_time="2025-05-01T09:00:00",
                ),
            ]
        }
        restored = support.import_activities(db, target.id, storage, far)

        assert (skipped.counts["activities"], skipped.counts["activities_skipped"]) == (0, 2)
        assert (restored.counts["activities"], restored.counts["activities_skipped"]) == (2, 0)

    def test_an_archive_that_lists_one_effort_twice_restores_both(self, db: Session, storage) -> None:
        target = make_user(db)
        entries = {"data/activities.json": [_row(name="one"), _row(_ARCHIVED_LEG, name="two")]}

        restored = support.import_activities(db, target.id, storage, entries)

        assert (restored.counts["activities"], restored.counts["activities_skipped"]) == (2, 0)

    def test_a_restored_activity_keeps_the_hidden_flag_it_was_archived_with(self, db: Session, storage) -> None:
        target = make_user(db)
        entries = {"data/activities.json": [_row(name="shown"), _row(_ARCHIVED_LEG, name="hidden", is_hidden=True)]}

        support.import_activities(db, target.id, storage, entries)

        rows = {
            a.name: a.is_hidden
            for a in activity_integration.list_user_activities_page(target.id, db, page_number=1, num_records=9)
        }
        assert rows == {"shown": False, "hidden": True}
