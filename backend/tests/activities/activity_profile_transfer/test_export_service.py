"""The activities' section of the profile export, on the real database and the platform's storage."""

import logging

import jasil.providers as platform_providers
import pytest
from sqlalchemy.orm import Session

import modules.activities.activity_exercise_titles.contracts as titles_contracts
import modules.activities.activity_exercise_titles.crud as titles_crud
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_media.integration_service as media_integration
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.utils as profile_utils
from tests._factories.activities import make_activity, make_activity_children, make_activity_media
from tests._factories.users import make_user
from tests.activities.activity_profile_transfer import support


@pytest.fixture
def storage(_publish_local_platform) -> platform_providers.StorageProvider:
    return _publish_local_platform.storage


class TestWhatTheArchiveHolds:
    def test_a_user_without_activities_gets_empty_entries_and_every_count_at_zero(self, db: Session, storage) -> None:
        user = make_user(db)

        exported = support.export_activities(db, user.id, storage)

        assert exported.after_commit is None
        assert exported.json("data/activities.json") == []
        assert set(exported.counts) >= support.COUNT_KEYS
        assert all(exported.counts[key] == 0 for key in support.COUNT_KEYS)

    def test_only_the_users_own_activities_are_exported_across_pages(self, db: Session, storage) -> None:
        owner = make_user(db)
        stranger = make_user(db)
        mine = [make_activity(db, owner.id, name=f"Run {index}") for index in range(3)]
        make_activity(db, stranger.id, name="Not mine")

        exported = support.export_activities(db, owner.id, storage, batch_size=2)

        listed = exported.json("data/activities.json")
        assert sorted(row["name"] for row in listed) == ["Run 0", "Run 1", "Run 2"]
        assert {row["id"] for row in listed} == {str(activity.id) for activity in mine}
        assert exported.counts["activities"] == 3

    def test_the_components_of_other_users_activities_are_left_out(self, db: Session, storage) -> None:
        owner = make_user(db)
        stranger = make_user(db)
        make_activity_children(db, make_activity(db, owner.id))
        make_activity_children(db, make_activity(db, stranger.id))

        exported = support.export_activities(db, owner.id, storage)

        assert len(exported.json("data/activity_laps.json")) == 1
        assert len(exported.json("data/activity_sets.json")) == 1
        assert len(exported.json("data/activity_streams.json")) == 1
        assert len(exported.json("data/activity_workout_steps.json")) == 1
        assert exported.counts["activity_laps"] == 1
        assert exported.counts["activity_workout_steps"] == 1

    def test_a_large_component_is_split_into_numbered_parts_and_a_small_one_stays_whole(
        self, db: Session, storage
    ) -> None:
        owner = make_user(db)
        for _ in range(3):
            make_activity_children(db, make_activity(db, owner.id))

        exported = support.export_activities(db, owner.id, storage, batch_size=2)

        parts = [name for name in exported.names if name.startswith("data/activity_laps_")]
        assert parts == ["data/activity_laps_000.json", "data/activity_laps_001.json", "data/activity_laps_002.json"]
        assert "data/activity_laps.json" not in exported.names
        assert exported.counts["activity_laps"] == 3
        assert len(exported.json("data/activity_workout_steps.json")) == 3

    def test_the_remainder_of_a_split_component_goes_in_a_last_shorter_part(self, db: Session, storage) -> None:
        owner = make_user(db)
        for _ in range(3):
            make_activity_children(db, make_activity(db, owner.id))

        exported = support.export_activities(db, owner.id, storage, batch_size=4)

        assert len(exported.json("data/activity_laps_000.json")) == 2
        assert len(exported.json("data/activity_laps_001.json")) == 1
        assert exported.counts["activity_laps"] == 3

    def test_a_component_that_fits_one_batch_keeps_its_plain_name(self, db: Session, storage) -> None:
        owner = make_user(db)
        for _ in range(2):
            make_activity_children(db, make_activity(db, owner.id))

        exported = support.export_activities(db, owner.id, storage)

        assert len(exported.json("data/activity_laps.json")) == 2
        assert not [name for name in exported.names if name.startswith("data/activity_laps_")]

    def test_a_component_nobody_has_still_gets_an_empty_entry(self, db: Session, storage) -> None:
        owner = make_user(db)
        make_activity(db, owner.id)

        exported = support.export_activities(db, owner.id, storage)

        assert exported.json("data/activity_laps.json") == []
        assert exported.json("data/activity_workout_steps.json") == []
        assert exported.counts["activity_laps"] == 0

    def test_the_exercise_titles_are_exported_once_and_counted(self, db: Session, storage) -> None:
        owner = make_user(db)
        make_activity(db, owner.id)
        titles_crud.create_activity_exercise_titles(
            [
                titles_contracts.ActivityExerciseTitlesCreate(exercise_category=1, exercise_name=2, wkt_step_name="A"),
                titles_contracts.ActivityExerciseTitlesCreate(exercise_category=3, exercise_name=4, wkt_step_name="B"),
            ],
            db,
        )

        exported = support.export_activities(db, owner.id, storage)

        assert exported.counts["activity_exercise_titles"] == len(exported.json("data/activity_exercise_titles.json"))
        assert {"A", "B"} <= {row["wkt_step_name"] for row in exported.json("data/activity_exercise_titles.json")}


class TestFilesAndMedia:
    def test_the_files_and_media_are_written_after_the_rows_are_committed(self, db: Session, storage) -> None:
        owner = make_user(db)
        activity = make_activity(db, owner.id)
        file_storage.store_activity_file(activity.id, ".gpx", support.GPX, storage)
        media_integration.store_media_blob(activity.id, "photo", ".png", support.png(), storage)

        before = support.export_activities(db, owner.id, storage, run_after_commit=False)
        assert before.after_commit is not None
        assert not [name for name in before.names if name.startswith(("activity_files/", "activity_media/"))]

        exported = support.export_activities(db, owner.id, storage)

        assert exported.entries[f"activity_files/{activity.id}.gpx"] == support.GPX
        assert exported.entries[f"activity_media/{activity.id}_photo.png"] == support.png()
        assert exported.counts["activity_files"] == 1
        assert exported.counts["media"] == 1

    def test_an_activity_without_a_file_or_media_adds_nothing(self, db: Session, storage) -> None:
        owner = make_user(db)
        make_activity(db, owner.id)

        exported = support.export_activities(db, owner.id, storage)

        assert exported.counts["activity_files"] == 0
        assert exported.counts["media"] == 0
        assert not [name for name in exported.names if name.startswith(("activity_files/", "activity_media/"))]

    def test_only_the_users_own_files_and_media_are_exported(self, db: Session, storage) -> None:
        owner = make_user(db)
        stranger = make_user(db)
        theirs = make_activity(db, stranger.id)
        file_storage.store_activity_file(theirs.id, ".gpx", support.GPX, storage)
        media_integration.store_media_blob(theirs.id, "photo", ".png", support.png(), storage)
        make_activity(db, owner.id)

        exported = support.export_activities(db, owner.id, storage)

        assert not [name for name in exported.names if name.startswith(("activity_files/", "activity_media/"))]

    def test_a_file_that_cannot_be_read_is_skipped_and_the_others_are_exported(
        self, db: Session, storage, caplog: pytest.LogCaptureFixture
    ) -> None:
        owner = make_user(db)
        broken = make_activity(db, owner.id)
        fine = make_activity(db, owner.id)
        for activity in (broken, fine):
            file_storage.store_activity_file(activity.id, ".gpx", support.GPX, storage)
        flaky = support.UnavailableStorage(storage, unreadable=(str(broken.id),))

        with caplog.at_level(logging.WARNING):
            exported = support.export_activities(db, owner.id, flaky)

        assert [name for name in exported.names if name.startswith("activity_files/")] == [
            f"activity_files/{fine.id}.gpx"
        ]
        assert exported.counts["activity_files"] == 1
        assert any(record.levelno == logging.WARNING for record in caplog.records)

    def test_an_unexpected_storage_error_fails_the_export(self, db: Session, storage) -> None:
        owner = make_user(db)
        make_activity(db, owner.id)

        with pytest.raises(RuntimeError, match="bug"):
            support.export_activities(db, owner.id, support.UnavailableStorage(storage, broken=RuntimeError("bug")))

    def test_a_media_listing_that_fails_skips_only_that_activitys_media(self, db: Session, storage) -> None:
        owner = make_user(db)
        activity = make_activity(db, owner.id)
        file_storage.store_activity_file(activity.id, ".gpx", support.GPX, storage)
        media_integration.store_media_blob(activity.id, "photo", ".png", support.png(), storage)

        exported = support.export_activities(db, owner.id, support.UnavailableStorage(storage, unlistable=True))

        assert exported.counts["media"] == 0
        assert exported.counts["activity_files"] == 1

    def test_a_media_blob_that_cannot_be_read_is_skipped_and_the_others_are_exported(
        self, db: Session, storage
    ) -> None:
        owner = make_user(db)
        activity = make_activity(db, owner.id)
        media_integration.store_media_blob(activity.id, "bad", ".png", support.png(10), storage)
        media_integration.store_media_blob(activity.id, "good", ".png", support.png(20), storage)

        exported = support.export_activities(
            db, owner.id, support.UnavailableStorage(storage, unreadable=(f"{activity.id}_bad",))
        )

        assert [name for name in exported.names if name.startswith("activity_media/")] == [
            f"activity_media/{activity.id}_good.png"
        ]
        assert exported.counts["media"] == 1

    def test_a_full_archive_fails_the_export_instead_of_ending_partial(self, db: Session, storage) -> None:
        owner = make_user(db)
        activity = make_activity(db, owner.id)
        file_storage.store_activity_file(activity.id, ".gpx", support.GPX, storage)

        class FullDisk(profile_utils.ZipArchiveWriter):
            def write_bytes(self, path: str, data: bytes) -> None:
                raise OSError("no space left")

        with pytest.raises(OSError, match="no space left"):
            support.export_activities(db, owner.id, storage, writer_type=FullDisk)

    def test_a_full_archive_fails_the_export_when_it_writes_media(self, db: Session, storage) -> None:
        owner = make_user(db)
        activity = make_activity(db, owner.id)
        media_integration.store_media_blob(activity.id, "photo", ".png", support.png(), storage)

        class FullDisk(profile_utils.ZipArchiveWriter):
            def write_bytes(self, path: str, data: bytes) -> None:
                raise OSError("no space left")

        with pytest.raises(OSError, match="no space left"):
            support.export_activities(db, owner.id, storage, writer_type=FullDisk)

    def test_the_time_limit_is_enforced_between_the_files_and_the_media(self, db: Session, storage) -> None:
        owner = make_user(db)
        activity = make_activity(db, owner.id)
        file_storage.store_activity_file(activity.id, ".gpx", support.GPX, storage)
        media_integration.store_media_blob(activity.id, "photo", ".png", support.png(), storage)
        make_activity_media(db, activity, f"{activity.id}_photo.png")

        def out_of_time() -> None:
            raise profile_exceptions.ExportTimeoutError("out of time")

        with pytest.raises(profile_exceptions.ExportTimeoutError):
            support.export_activities(db, owner.id, storage, check_timeout=out_of_time)


class TestLimits:
    def test_a_memory_limit_hit_while_reading_stops_the_export(self, db: Session, storage) -> None:
        owner = make_user(db)
        make_activity(db, owner.id)

        def too_much(_operation: str) -> None:
            raise profile_exceptions.MemoryAllocationError("memory limit exceeded")

        with pytest.raises(profile_exceptions.MemoryAllocationError):
            support.export_activities(db, owner.id, storage, check_memory=too_much)

    def test_a_memory_limit_hit_with_no_activities_stops_the_export_before_anything_is_written(
        self, db: Session, storage
    ) -> None:
        owner = make_user(db)
        operations: list[str] = []

        def too_much(operation: str) -> None:
            operations.append(operation)
            raise profile_exceptions.MemoryAllocationError("memory limit exceeded")

        with pytest.raises(profile_exceptions.MemoryAllocationError):
            support.export_activities(db, owner.id, storage, check_memory=too_much)

        assert len(operations) == 1
