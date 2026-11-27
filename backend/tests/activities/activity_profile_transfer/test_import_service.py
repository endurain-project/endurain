"""The activities' section of the profile import, on the real database and the platform's storage."""

import uuid
from typing import Any

import jasil.providers as platform_providers
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.models as titles_models
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_laps.models as laps_models
import modules.activities.activity_media.integration_service as media_integration
import modules.activities.activity_media.models as media_models
import modules.activities.activity_streams.crud as streams_crud
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.utils as profile_utils
from tests._factories.activities import make_activity, make_activity_children, make_activity_media
from tests._factories.gears import make_gear
from tests._factories.users import make_user
from tests.activities.activity_profile_transfer import support

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
_ARCHIVED_ACTIVITY = uuid.UUID("00000000-0000-4000-8000-00000000a003")
_ARCHIVED_GEAR = uuid.UUID("00000000-0000-4000-8000-00000000a001")
_UNKNOWN_ACTIVITY = uuid.UUID("00000000-0000-4000-8000-00000000a005")


@pytest.fixture
def storage(_publish_local_platform) -> platform_providers.StorageProvider:
    return _publish_local_platform.storage


def _activity_row(**overrides: Any) -> dict[str, Any]:
    """One archived activity, as an export writes it."""
    row: dict[str, Any] = {
        "id": str(_ARCHIVED_ACTIVITY),
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


def _restored(db: Session, user_id: uuid.UUID) -> list[activity_schema.ActivityRead]:
    return activity_integration.list_user_activities_page(user_id, db, page_number=1, num_records=100)


def _seed_source(db: Session, storage: platform_providers.StorageProvider) -> tuple[uuid.UUID, dict[str, bytes]]:
    """Export an account with two activities, each with children, a file and a media blob."""
    source = make_user(db)
    for index in range(2):
        activity = make_activity(db, source.id, name=f"Ride {index}", distance=5000 + index)
        make_activity_children(db, activity)
        make_activity_media(db, activity, f"{activity.id}_photo.png")
        file_storage.store_activity_file(activity.id, ".gpx", support.GPX, storage)
        media_integration.store_media_blob(activity.id, "photo", ".png", support.png(index), storage)
    return source.id, support.export_activities(db, source.id, storage, batch_size=2).entries


class TestRestoreProfile:
    def test_an_empty_archive_restores_nothing_and_reports_every_count_at_zero(self, db: Session, storage) -> None:
        user = make_user(db)

        restored = support.import_activities(db, user.id, storage, {"data/activities.json": []})

        assert restored.after_commit is None
        assert set(restored.counts) >= support.COUNT_KEYS
        assert all(restored.counts[key] == 0 for key in support.COUNT_KEYS)
        assert _restored(db, user.id) == []

    def test_an_archive_that_carries_other_files_has_no_deferred_work(self, db: Session, storage) -> None:
        user = make_user(db)

        restored = support.import_activities(
            db, user.id, storage, {"data/activities.json": [], "user_images/1.png": b"x"}
        )

        assert restored.after_commit is None

    @pytest.mark.parametrize("folder", ["activity_files", "activity_media"])
    def test_files_or_media_in_the_archive_give_deferred_work(self, db: Session, storage, folder: str) -> None:
        user = make_user(db)

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {"data/activities.json": [], f"{folder}/{_ARCHIVED_ACTIVITY}.gpx": b"x"},
            run_after_commit=False,
        )

        assert restored.after_commit is not None

    def test_a_whole_export_is_restored_under_the_importing_user_with_new_ids(self, db: Session, storage) -> None:
        source_id, entries = _seed_source(db, storage)
        target = make_user(db)

        restored = support.import_activities(db, target.id, storage, entries)

        rows = sorted(_restored(db, target.id), key=lambda activity: activity.name)
        assert [(activity.name, activity.distance) for activity in rows] == [("Ride 0", 5000), ("Ride 1", 5001)]
        assert all(activity.user_id == target.id for activity in rows)
        assert {activity.id for activity in rows}.isdisjoint({a.id for a in _restored(db, source_id)})
        assert restored.counts["activities"] == 2
        assert restored.counts["activity_laps"] == 2
        assert restored.counts["activity_sets"] == 2
        assert restored.counts["activity_samples"] == 2
        assert restored.counts["activity_streams"] == 0
        assert restored.counts["activity_workout_steps"] == 2
        assert restored.counts["activity_media"] == 2
        lap_owners = db.scalars(select(laps_models.ActivityLaps.activity_id)).all()
        assert {activity.id for activity in rows} <= set(lap_owners)

    def test_an_archive_with_old_streams_is_restored_as_samples(self, db: Session, storage) -> None:
        target = make_user(db)
        entries = {
            "data/activities.json": [_activity_row()],
            "data/activity_streams.json": [
                {
                    "id": str(uuid.uuid4()),
                    "activity_id": str(_ARCHIVED_ACTIVITY),
                    "stream_type": 1,
                    "stream_waypoints": [
                        {"time": "2024-01-01T08:00:00", "hr": 120},
                        {"time": "2024-01-01T08:00:02", "hr": 130},
                    ],
                }
            ],
        }

        restored = support.import_activities(db, target.id, storage, entries)

        [activity] = _restored(db, target.id)
        samples = streams_crud.get_activity_samples(activity.id, db)
        assert samples is not None
        assert (samples.offsets_ms, samples.heart_rate) == ([0, 2000], [120.0, 130.0])
        assert (restored.counts["activity_streams"], restored.counts["activity_samples"]) == (1, 0)
        assert streams_crud.get_activity_streams(activity.id, db) == []

    def test_the_files_and_media_are_stored_under_the_new_activity_ids(self, db: Session, storage) -> None:
        _, entries = _seed_source(db, storage)
        target = make_user(db)

        restored = support.import_activities(db, target.id, storage, entries)

        for activity in _restored(db, target.id):
            assert file_storage.get_activity_file(activity.id, storage) == (f"{activity.id}.gpx", support.GPX)
            blobs = media_integration.list_media_blobs(activity.id, storage)
            assert [key for key, _ in blobs] == [f"{activity.id}_photo.png"]
        assert restored.counts["activity_files"] == 2
        assert restored.counts["media"] == 2

    def test_the_files_wait_for_the_deferred_work(self, db: Session, storage) -> None:
        _, entries = _seed_source(db, storage)
        target = make_user(db)

        restored = support.import_activities(db, target.id, storage, entries, run_after_commit=False)

        activity = _restored(db, target.id)[0]
        assert file_storage.get_activity_file(activity.id, storage) is None
        assert restored.counts["activity_files"] == 0
        assert restored.after_commit is not None
        restored.after_commit()
        assert file_storage.get_activity_file(activity.id, storage) is not None

    def test_a_restore_publishes_no_activity_created_event(self, db: Session, storage, _publish_local_platform) -> None:
        published: list[object] = []
        _publish_local_platform.events.subscribe(activity_events.ACTIVITY_CREATED, published.append)
        user = make_user(db)

        support.import_activities(db, user.id, storage, {"data/activities.json": [_activity_row()]})

        assert len(_restored(db, user.id)) == 1
        assert published == []


class TestRestoreActivities:
    def test_an_activity_as_exported_is_imported_without_the_fields_the_server_derives(
        self, db: Session, storage
    ) -> None:
        user = make_user(db)
        stranger = make_user(db)
        exported = profile_utils.model_to_dict(
            activity_schema.ActivityRead(
                id=_ARCHIVED_ACTIVITY,
                user_id=stranger.id,
                version=7,
                distance=1000,
                name="Morning Run",
                activity_type=1,
                start_time="2024-01-01T08:00:00",
                end_time="2024-01-01T09:00:00",
                total_elapsed_time=3600.0,
                total_timer_time=3500.0,
                is_hidden=False,
                **{flag: False for flag in _PRIVACY_FLAGS},
            )
        )

        support.import_activities(db, user.id, storage, {"data/activities.json": [exported]})

        [activity] = _restored(db, user.id)
        assert (activity.user_id, activity.name) == (user.id, "Morning Run")
        assert activity.id != _ARCHIVED_ACTIVITY
        assert activity.version == 1
        assert _restored(db, stranger.id) == []

    def test_a_gear_restored_earlier_replaces_the_archived_gear_id(self, db: Session, storage) -> None:
        user = make_user(db)
        gear = make_gear(db, user.id)

        support.import_activities(
            db,
            user.id,
            storage,
            {"data/activities.json": [_activity_row(gear_id=str(_ARCHIVED_GEAR))]},
            ids={"gears": {_ARCHIVED_GEAR: gear.id}},
        )

        [activity] = _restored(db, user.id)
        assert activity.gear_id == gear.id

    def test_a_gear_that_was_not_restored_leaves_the_activity_without_gear(self, db: Session, storage) -> None:
        user = make_user(db)

        support.import_activities(
            db, user.id, storage, {"data/activities.json": [_activity_row(gear_id=str(_ARCHIVED_GEAR))]}
        )

        [activity] = _restored(db, user.id)
        assert activity.gear_id is None

    def test_an_activity_with_an_integer_id_is_restored_but_gets_no_components(self, db: Session, storage) -> None:
        user = make_user(db)
        restored = support.import_activities(
            db,
            user.id,
            storage,
            {
                "data/activities.json": [_activity_row(id=1)],
                "data/activity_laps.json": [{"activity_id": 1, "start_time": "2024-01-01T08:00:00"}],
            },
        )

        assert len(_restored(db, user.id)) == 1
        assert restored.counts["activities"] == 1
        assert restored.counts["activity_laps"] == 0

    def test_an_activity_without_an_id_is_restored_but_gets_no_components(self, db: Session, storage) -> None:
        user = make_user(db)
        row = _activity_row()
        del row["id"]

        restored = support.import_activities(db, user.id, storage, {"data/activities.json": [row]})

        assert len(_restored(db, user.id)) == 1
        assert restored.counts["activities"] == 1
        assert restored.after_commit is None

    def test_an_archive_over_the_activity_limit_stages_nothing(self, db: Session, storage) -> None:
        user = make_user(db)
        rows = [_activity_row(), _activity_row(id=str(_UNKNOWN_ACTIVITY))]

        with pytest.raises(profile_exceptions.ActivityLimitError):
            support.import_activities(db, user.id, storage, {"data/activities.json": rows}, max_activities=1)

        assert _restored(db, user.id) == []

    def test_activities_are_restored_batch_by_batch(self, db: Session, storage) -> None:
        user = make_user(db)
        rows = [_activity_row(id=str(uuid.UUID(int=index + 1)), name=f"Run {index}") for index in range(5)]

        restored = support.import_activities(db, user.id, storage, {"data/activities.json": rows}, batch_size=2)

        assert sorted(activity.name for activity in _restored(db, user.id)) == [f"Run {index}" for index in range(5)]
        assert restored.counts["activities"] == 5

    def test_the_time_limit_stops_the_restore_before_the_first_activity(self, db: Session, storage) -> None:
        user = make_user(db)

        def out_of_time() -> None:
            raise profile_exceptions.ImportTimeoutError("out of time")

        with pytest.raises(profile_exceptions.ImportTimeoutError):
            support.import_activities(
                db, user.id, storage, {"data/activities.json": [_activity_row()]}, check_timeout=out_of_time
            )

        assert _restored(db, user.id) == []

    def test_a_memory_limit_hit_while_restoring_stops_the_import(self, db: Session, storage) -> None:
        user = make_user(db)

        def too_much(_operation: str) -> None:
            raise profile_exceptions.MemoryAllocationError("memory limit exceeded")

        with pytest.raises(profile_exceptions.MemoryAllocationError):
            support.import_activities(
                db, user.id, storage, {"data/activities.json": [_activity_row()]}, check_memory=too_much
            )


class TestComponents:
    def test_only_the_components_of_a_restored_activity_are_restored(self, db: Session, storage) -> None:
        user = make_user(db)
        record = {"activity_id": str(_ARCHIVED_ACTIVITY), "start_time": "2024-01-01T08:00:00"}
        stray = {"activity_id": str(_UNKNOWN_ACTIVITY), "start_time": "2024-01-01T08:00:00"}

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {"data/activities.json": [_activity_row()], "data/activity_laps.json": [record, stray]},
        )

        [activity] = _restored(db, user.id)
        laps = db.scalars(select(laps_models.ActivityLaps).where(laps_models.ActivityLaps.activity_id == activity.id))
        assert len(laps.all()) == 1
        assert restored.counts["activity_laps"] == 1

    def test_split_parts_are_restored_in_name_order(self, db: Session, storage) -> None:
        user = make_user(db)
        archived = _ARCHIVED_ACTIVITY
        laps = [{"activity_id": str(archived), "start_time": f"2024-01-01T08:0{index}:00"} for index in range(3)]

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {
                "data/activities.json": [_activity_row()],
                "data/activity_laps_001.json": [laps[1]],
                "data/activity_laps_000.json": [laps[0]],
                "data/activity_laps_002.json": [laps[2]],
                "data/activity_laps.json": [laps[0]],
            },
        )

        assert restored.counts["activity_laps"] == 3

    def test_a_part_that_is_not_json_is_skipped_and_the_other_parts_are_restored(self, db: Session, storage) -> None:
        user = make_user(db)
        lap = {"activity_id": str(_ARCHIVED_ACTIVITY), "start_time": "2024-01-01T08:00:00"}

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {
                "data/activities.json": [_activity_row()],
                "data/activity_laps_000.json": b"not-valid-json",
                "data/activity_laps_001.json": [lap],
            },
        )

        assert restored.counts["activity_laps"] == 1
        assert restored.counts["activities"] == 1

    def test_a_part_larger_than_the_json_limit_is_skipped(self, db: Session, storage) -> None:
        user = make_user(db)
        lap = {"activity_id": str(_ARCHIVED_ACTIVITY), "start_time": "2024-01-01T08:00:00"}

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {
                "data/activities.json": [_activity_row()],
                "data/activity_laps_000.json": [lap] * 200,
                "data/activity_laps_001.json": [lap],
            },
            max_json_bytes=1000,
        )

        assert restored.counts["activity_laps"] == 1

    def test_a_part_that_is_not_a_list_is_skipped(self, db: Session, storage) -> None:
        user = make_user(db)
        lap = {"activity_id": str(_ARCHIVED_ACTIVITY), "start_time": "2024-01-01T08:00:00"}

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {
                "data/activities.json": [_activity_row()],
                "data/activity_laps_000.json": {"not": "a list"},
                "data/activity_laps_001.json": [lap],
            },
        )

        assert restored.counts["activity_laps"] == 1

    def test_a_media_record_whose_key_leaves_the_media_area_is_not_restored(self, db: Session, storage) -> None:
        """The archive is untrusted: such a value would address a blob outside the flat media area."""
        user = make_user(db)
        records = [
            {"activity_id": str(_ARCHIVED_ACTIVITY), "media_path": f"{_ARCHIVED_ACTIVITY}_ok.jpg", "media_type": 1},
            {
                "activity_id": str(_ARCHIVED_ACTIVITY),
                "media_path": f"../../etc/{_ARCHIVED_ACTIVITY}_passwd.jpg",
                "media_type": 1,
            },
            {"activity_id": str(_ARCHIVED_ACTIVITY), "media_path": "nounderscore.jpg", "media_type": 1},
        ]

        restored = support.import_activities(
            db,
            user.id,
            storage,
            {"data/activities.json": [_activity_row()], "data/activity_media.json": records},
        )

        assert restored.counts["activity_media"] == 1
        [activity] = _restored(db, user.id)
        stored = db.scalars(
            select(media_models.ActivityMedia.media_path).where(media_models.ActivityMedia.activity_id == activity.id)
        ).all()
        assert stored == [f"{activity.id}_ok.jpg"]

    def test_the_exercise_titles_are_restored_once(self, db: Session, storage) -> None:
        user = make_user(db)
        titles = [
            {"exercise_category": 1, "exercise_name": 2, "wkt_step_name": "Bench"},
            {"exercise_category": 3, "exercise_name": 4, "wkt_step_name": "Row"},
        ]
        before = db.scalar(select(func.count()).select_from(titles_models.ActivityExerciseTitles)) or 0

        restored = support.import_activities(
            db, user.id, storage, {"data/activities.json": [], "data/activity_exercise_titles.json": titles}
        )

        after = db.scalar(select(func.count()).select_from(titles_models.ActivityExerciseTitles)) or 0
        assert restored.counts["activity_exercise_titles"] == 2
        assert after - before == 2


class TestRestoredFiles:
    def _import_file(self, db: Session, storage, name: str, data: bytes, **kwargs: Any) -> tuple[Any, uuid.UUID]:
        user = make_user(db)
        restored = support.import_activities(
            db,
            user.id,
            storage,
            {"data/activities.json": [_activity_row()], name: data},
            **kwargs,
        )
        [activity] = _restored(db, user.id)
        return restored, activity.id

    @pytest.mark.parametrize("extension", [".gpx"])
    def test_a_valid_file_is_stored_under_the_new_id(self, db: Session, storage, extension: str) -> None:
        restored, activity_id = self._import_file(
            db, storage, f"activity_files/{_ARCHIVED_ACTIVITY}{extension}", support.GPX
        )

        assert file_storage.get_activity_file(activity_id, storage) == (f"{activity_id}{extension}", support.GPX)
        assert restored.counts["activity_files"] == 1

    def test_an_invalid_file_is_dropped(self, db: Session, storage) -> None:
        restored, activity_id = self._import_file(
            db, storage, f"activity_files/{_ARCHIVED_ACTIVITY}.gpx", b"this is not an activity file"
        )

        assert file_storage.get_activity_file(activity_id, storage) is None
        assert restored.counts["activity_files"] == 0

    @pytest.mark.parametrize(
        "name",
        [
            f"activity_files/{_UNKNOWN_ACTIVITY}.gpx",
            "activity_files/1.gpx",
            "activity_files/notes.gpx",
            f"activity_files/{_ARCHIVED_ACTIVITY}.txt",
        ],
    )
    def test_a_file_that_names_no_restored_activity_is_skipped(self, db: Session, storage, name: str) -> None:
        restored, activity_id = self._import_file(db, storage, name, support.GPX)

        assert file_storage.get_activity_file(activity_id, storage) is None
        assert restored.counts["activity_files"] == 0

    def test_a_valid_image_is_stored_under_the_new_id(self, db: Session, storage) -> None:
        restored, activity_id = self._import_file(
            db, storage, f"activity_media/{_ARCHIVED_ACTIVITY}_photo.png", support.png()
        )

        assert media_integration.list_media_blobs(activity_id, storage) == [(f"{activity_id}_photo.png", support.png())]
        assert restored.counts["media"] == 1

    def test_an_invalid_image_is_never_stored(self, db: Session, storage) -> None:
        restored, activity_id = self._import_file(
            db, storage, f"activity_media/{_ARCHIVED_ACTIVITY}_bad.png", b"not an image"
        )

        assert media_integration.list_media_blobs(activity_id, storage) == []
        assert restored.counts["media"] == 0

    @pytest.mark.parametrize(
        "name",
        [
            f"activity_media/{_UNKNOWN_ACTIVITY}_photo.png",
            "activity_media/abc_photo.png",
            "activity_media/nounderscore.png",
            f"activity_media/{_ARCHIVED_ACTIVITY}_photo.gif",
        ],
    )
    def test_a_media_file_that_cannot_be_matched_is_skipped(self, db: Session, storage, name: str) -> None:
        restored, activity_id = self._import_file(db, storage, name, support.png())

        assert media_integration.list_media_blobs(activity_id, storage) == []
        assert restored.counts["media"] == 0

    def test_the_memory_check_runs_for_the_files_and_the_media(self, db: Session, storage) -> None:
        user = make_user(db)
        operations: list[str] = []

        support.import_activities(
            db,
            user.id,
            storage,
            {"data/activities.json": [], f"activity_files/{_ARCHIVED_ACTIVITY}.gpx": support.GPX},
            check_memory=operations.append,
        )

        assert {"activity files import", "activity media import"} <= set(operations)
