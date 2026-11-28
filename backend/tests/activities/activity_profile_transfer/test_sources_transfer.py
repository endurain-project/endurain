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

    def test_a_source_the_account_already_holds_is_left_out_and_the_import_goes_on(self, db: Session, storage) -> None:
        source_user = make_user(db)
        make_activity(db, source_user.id, name="one", strava_activity_id=7)
        entries = support.export_activities(db, source_user.id, storage).entries

        restored = support.import_activities(db, source_user.id, storage, entries)

        assert restored.counts["activities"] == 1
        assert restored.counts["activity_sources"] == 0
        assert len(_sources_of(db, source_user.id)) == 1

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
