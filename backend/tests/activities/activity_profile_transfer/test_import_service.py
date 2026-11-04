"""Tests for the activities' section of the profile data import."""

import json
import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_profile_transfer.import_service as import_service
import modules.users.users_profile.contracts as users_profile_contracts
import modules.users.users_profile.utils as profile_utils
from modules.users.users_profile.exceptions import (
    ActivityLimitError,
    FileFormatError,
    MemoryAllocationError,
)


def _zip(files: dict[str, object]) -> zipfile.ZipFile:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, bytes) else json.dumps(data))
    return zipfile.ZipFile(BytesIO(buf.getvalue()))


def _ctx(
    files: dict[str, object] | None = None,
    *,
    ids=None,
    max_activities: int = 10000,
    batch_size: int = 125,
    storage=None,
    check_memory=None,
    check_timeout=None,
):
    archive = profile_utils.ZipArchiveReader(
        _zip(files or {}),
        max_json_bytes=128 * 1024 * 1024,
        max_uncompressed_bytes=1024 * 1024 * 1024,
        max_memory_mb=1024,
        enable_memory_monitoring=False,
    )

    def check_activity_count(count: int) -> None:
        if count > max_activities:
            raise ActivityLimitError(f"Too many activities ({count})")

    return users_profile_contracts.ProfileImportContext(
        user_id=1,
        db=MagicMock(spec=Session),
        storage=storage or MagicMock(),
        archive=archive,
        counts={},
        ids=ids if ids is not None else {},
        batch_size=batch_size,
        check_memory=check_memory or MagicMock(),
        check_timeout=check_timeout or MagicMock(),
        check_activity_count=check_activity_count,
    )


_ACTIVITY = {
    "id": 1,
    "distance": 1000,
    "name": "Morning Run",
    "activity_type": 1,
    "start_time": "2024-01-01T08:00:00",
    "end_time": "2024-01-01T09:00:00",
}


def _no_contributors():
    registry = import_service.activities_contributor_registry
    return (
        patch.object(registry, "profile_activity_contributors", return_value=()),
        patch.object(registry, "profile_global_contributors", return_value=()),
    )


class TestRestoreProfile:
    def test_an_empty_archive_restores_nothing_and_reports_zero_counts(self) -> None:
        import module_registry

        module_registry.configure_activity_contributors()
        ctx = _ctx({"data/activities.json": []})

        assert import_service.restore_profile(ctx) is None

        registry = import_service.activities_contributor_registry
        expected = {"activities", "activity_files", "media"}
        expected |= {c.count_key for c in registry.profile_activity_contributors()}
        expected |= {c.count_key for c in registry.profile_global_contributors()}
        assert expected <= set(ctx.counts)
        assert all(ctx.counts[key] == 0 for key in expected)

    def test_there_is_no_after_commit_work_without_activity_files_or_media(self) -> None:
        ctx = _ctx({"data/activities.json": [], "user_images/1.png": b"x"})
        activity_patch, global_patch = _no_contributors()
        with activity_patch, global_patch:
            assert import_service.restore_profile(ctx) is None

    @pytest.mark.parametrize("name", ["activity_files/1.gpx", "activity_media/1_a.png"])
    async def test_files_or_media_in_the_archive_return_the_after_commit_work(self, name) -> None:
        ctx = _ctx({"data/activities.json": [], name: b"x"})
        activity_patch, global_patch = _no_contributors()
        with (
            activity_patch,
            global_patch,
            patch.object(import_service, "_restore_activity_files", new_callable=AsyncMock) as files,
            patch.object(import_service, "_restore_activity_media", new_callable=AsyncMock) as media,
        ):
            restore_files = import_service.restore_profile(ctx)
            assert restore_files is not None
            files.assert_not_called()
            await restore_files()

        files.assert_awaited_once_with(ctx, {})
        media.assert_awaited_once_with(ctx, {})

    async def test_the_after_commit_work_holds_the_restored_activity_ids(self) -> None:
        ctx = _ctx({"data/activities.json": [_ACTIVITY], "activity_files/1.gpx": b"x"})
        ctx.counts["activities"] = 0
        activity_patch, global_patch = _no_contributors()
        restored = MagicMock()
        restored.id = 10
        with (
            activity_patch,
            global_patch,
            patch.object(import_service.activity_integration, "restore_activity", return_value=restored),
            patch.object(import_service, "_restore_activity_files", new_callable=AsyncMock) as files,
            patch.object(import_service, "_restore_activity_media", new_callable=AsyncMock),
        ):
            restore_files = import_service.restore_profile(ctx)
            assert restore_files is not None
            await restore_files()

        files.assert_awaited_once_with(ctx, {1: 10})
        assert ctx.ids == {}

    def test_the_gear_ids_published_by_the_gear_section_are_read(self) -> None:
        ctx = _ctx({"data/activities.json": []}, ids={"gears": {5: 20}})
        activity_patch, global_patch = _no_contributors()
        with (
            activity_patch,
            global_patch,
            patch.object(import_service, "_restore_activities", return_value={}) as restore,
        ):
            import_service.restore_profile(ctx)

        restore.assert_called_once_with(ctx, {5: 20})


class TestRestoreActivities:
    def test_an_archive_without_activities_gives_an_empty_mapping(self) -> None:
        assert import_service._restore_activities(_ctx({"data/activities.json": []}), {}) == {}

    def test_the_activity_limit_is_checked_by_the_context(self) -> None:
        ctx = _ctx({"data/activities.json": [{"id": 1}, {"id": 2}]}, max_activities=1)
        activity_patch, global_patch = _no_contributors()
        with activity_patch, global_patch, pytest.raises(ActivityLimitError):
            import_service._restore_activities(ctx, {})

    def test_a_batch_checks_the_timeout_and_memory_with_the_batch_operation_name(self) -> None:
        check_memory = MagicMock()
        check_timeout = MagicMock()
        ctx = _ctx(
            {"data/activities.json": [_ACTIVITY, {**_ACTIVITY, "id": 2}]},
            batch_size=1,
            check_memory=check_memory,
            check_timeout=check_timeout,
        )
        ctx.counts["activities"] = 0
        activity_patch, global_patch = _no_contributors()
        restored = MagicMock()
        restored.id = 10
        with (
            activity_patch,
            global_patch,
            patch.object(import_service.activity_integration, "restore_activity", return_value=restored),
            patch.object(import_service, "_restore_activity_components"),
        ):
            import_service._restore_activities(ctx, {})

        assert check_timeout.call_count == 2
        assert [call.args[0] for call in check_memory.call_args_list] == ["activities batch 1", "activities batch 2"]

    def test_a_single_batch_maps_gears_and_activity_ids(self) -> None:
        ctx = _ctx(
            {
                "data/activities.json": [
                    {
                        "id": 1,
                        "gear_id": 5,
                        "distance": 1000,
                        "name": "Morning Run",
                        "activity_type": 1,
                        "start_time": "2024-01-01T08:00:00",
                        "end_time": "2024-01-01T09:00:00",
                    }
                ],
                "data/activity_laps_000.json": [{"activity_id": 1, "lap_index": 1}],
            }
        )
        ctx.counts["activities"] = 0
        activity_patch, global_patch = _no_contributors()
        restored = MagicMock()
        restored.id = 10
        with (
            activity_patch,
            global_patch,
            patch.object(import_service.activity_integration, "restore_activity", return_value=restored) as restore,
            patch.object(import_service, "_restore_activity_components") as components,
        ):
            mapping = import_service._restore_activities(ctx, {5: 20})

        assert mapping == {1: 10}
        assert ctx.counts["activities"] == 1
        assert restore.call_args.args[0].gear_id == 20
        components.assert_called_once()
        # The restore functions only stage; the import commits once at the end.
        ctx.db.commit.assert_not_called()

    def test_an_activity_as_exported_is_imported(self) -> None:
        """An archive's activity is the full read shape, with its version and the URLs and media the server derives."""
        exported = profile_utils.model_to_dict(
            activity_schema.ActivityRead(
                id=1,
                user_id=3,
                version=2,
                distance=1000,
                name="Morning Run",
                activity_type=1,
                start_time="2024-01-01T08:00:00",
                end_time="2024-01-01T09:00:00",
            )
        )
        ctx = _ctx({"data/activities.json": [exported]})
        ctx.counts["activities"] = 0
        activity_patch, global_patch = _no_contributors()
        restored = MagicMock()
        restored.id = 10
        with (
            activity_patch,
            global_patch,
            patch.object(import_service.activity_integration, "restore_activity", return_value=restored) as restore,
            patch.object(import_service, "_restore_activity_components"),
        ):
            mapping = import_service._restore_activities(ctx, {})

        assert mapping == {1: 10}
        imported = restore.call_args.args[0]
        assert (imported.user_id, imported.name) == (1, "Morning Run")

    def test_an_activity_without_an_id_is_restored_but_gets_no_components(self) -> None:
        ctx = _ctx(
            {
                "data/activities.json": [
                    {
                        "distance": 1000,
                        "name": "Test",
                        "activity_type": 1,
                        "gear_id": 5,
                        "start_time": "2024-01-01T08:00:00",
                        "end_time": "2024-01-01T09:00:00",
                    }
                ],
            }
        )
        ctx.counts["activities"] = 0
        activity_patch, global_patch = _no_contributors()
        restored = MagicMock()
        restored.id = 10
        with (
            activity_patch,
            global_patch,
            patch.object(import_service.activity_integration, "restore_activity", return_value=restored),
            patch.object(import_service, "_restore_activity_components") as components,
        ):
            mapping = import_service._restore_activities(ctx, {5: 20})

        assert mapping == {}
        assert ctx.counts["activities"] == 1
        components.assert_not_called()


class TestRestoreActivityComponents:
    @pytest.mark.parametrize(
        ("key", "count_key"),
        [
            ("laps", "activity_laps"),
            ("sets", "activity_sets"),
            ("streams", "activity_streams"),
            ("workout_steps", "activity_workout_steps"),
        ],
    )
    def test_the_contributor_restores_and_its_count_is_kept(self, key: str, count_key: str) -> None:
        ctx = _ctx()
        ctx.counts[count_key] = 0
        contributor = MagicMock(key=key, count_key=count_key)
        contributor.restore.return_value = 1
        records = [{"activity_id": 1}]
        new_activity = MagicMock(id=10, user_id=1)

        with patch.object(
            import_service.activities_contributor_registry, "profile_activity_contributors", return_value=(contributor,)
        ):
            import_service._restore_activity_components(ctx, {key: records}, 1, new_activity)

        contributor.restore.assert_called_once_with(records, 1, new_activity, ctx.db)
        assert ctx.counts[count_key] == 1

    def test_a_contributor_without_records_gets_an_empty_list(self) -> None:
        ctx = _ctx()
        ctx.counts["activity_laps"] = 0
        contributor = MagicMock(key="laps", count_key="activity_laps")
        contributor.restore.return_value = 0
        new_activity = MagicMock(id=10, user_id=1)

        with patch.object(
            import_service.activities_contributor_registry, "profile_activity_contributors", return_value=(contributor,)
        ):
            import_service._restore_activity_components(ctx, {}, 1, new_activity)

        contributor.restore.assert_called_once_with([], 1, new_activity, ctx.db)
        assert ctx.counts["activity_laps"] == 0

    @staticmethod
    def _media_restore(records):
        import modules.activities.activity_media.integration_service as media_integration

        ctx = _ctx()
        ctx.counts["activity_media"] = 0
        contributor = media_integration.profile_contributor()
        with (
            patch.object(
                import_service.activities_contributor_registry,
                "profile_activity_contributors",
                return_value=(contributor,),
            ),
            patch.object(media_integration, "_restore_media_records") as restore_media,
        ):
            import_service._restore_activity_components(ctx, {"media": records}, 1, MagicMock(id=10, user_id=1))
        return ctx, restore_media

    def test_media_with_a_valid_key_is_restored(self) -> None:
        records = [{"activity_id": 1, "media_path": "1_photo.jpg", "media_type": 1}]
        ctx, restore_media = self._media_restore(records)

        restore_media.assert_called_once()
        assert records[0]["media_path"] == "1_photo.jpg"
        assert ctx.counts["activity_media"] == 1

    def test_a_key_carrying_a_path_separator_is_skipped(self) -> None:
        """The archive is untrusted: such a value would address a blob outside the flat media area."""
        ctx, restore_media = self._media_restore(
            [{"activity_id": 1, "media_path": "../../etc/1_passwd.jpg", "media_type": 1}]
        )

        restore_media.assert_not_called()
        assert ctx.counts["activity_media"] == 0

    def test_a_key_without_the_activity_prefix_is_skipped(self) -> None:
        ctx, restore_media = self._media_restore(
            [{"activity_id": 1, "media_path": "nounderscore.jpg", "media_type": 1}]
        )

        restore_media.assert_not_called()
        assert ctx.counts["activity_media"] == 0

    def test_only_the_records_of_the_activity_are_restored(self) -> None:
        ctx, _ = self._media_restore(
            [
                {"activity_id": 1, "media_path": "1_a.jpg", "media_type": 1},
                {"activity_id": 1, "media_path": "1_b.jpg", "media_type": 1},
                {"activity_id": 2, "media_path": "2_c.jpg", "media_type": 1},
            ]
        )

        assert ctx.counts["activity_media"] == 2


class TestRestoreGlobalComponents:
    def test_each_contribution_is_restored_once(self) -> None:
        ctx = _ctx()
        ctx.counts["activity_exercise_titles"] = 0
        contributor = MagicMock(
            key="exercise_titles",
            archive_path="data/activity_exercise_titles.json",
            count_key="activity_exercise_titles",
        )
        contributor.restore.return_value = 2
        records = [{"exercise_name": 1}, {"exercise_name": 2}]
        archive = MagicMock()
        archive.load_json.return_value = records
        ctx = users_profile_contracts.ProfileImportContext(
            user_id=ctx.user_id,
            db=ctx.db,
            storage=ctx.storage,
            archive=archive,
            counts=ctx.counts,
            ids=ctx.ids,
            batch_size=ctx.batch_size,
            check_memory=ctx.check_memory,
            check_timeout=ctx.check_timeout,
            check_activity_count=ctx.check_activity_count,
        )

        with patch.object(
            import_service.activities_contributor_registry, "profile_global_contributors", return_value=(contributor,)
        ):
            import_service._restore_global_components(ctx)

        archive.load_json.assert_called_once_with(contributor.archive_path, check_memory=False)
        contributor.restore.assert_called_once_with(records, ctx.db)
        assert ctx.counts["activity_exercise_titles"] == 2
        # Restore only stages the rows; the whole import commits once, later.
        ctx.db.commit.assert_not_called()


class TestSplitFiles:
    def test_split_files_are_returned_sorted(self) -> None:
        file_list = frozenset(
            {
                "data/activity_laps_000.json",
                "data/activity_laps_001.json",
                "data/activity_laps.json",
                "data/other.json",
            }
        )
        assert import_service._get_split_files_list(file_list, "data/activity_laps") == [
            "data/activity_laps_000.json",
            "data/activity_laps_001.json",
        ]

    def test_falls_back_to_the_single_file(self) -> None:
        file_list = frozenset({"data/activity_laps.json", "data/other.json"})
        assert import_service._get_split_files_list(file_list, "data/activity_laps") == ["data/activity_laps.json"]

    def test_no_files_gives_an_empty_list(self) -> None:
        assert import_service._get_split_files_list(frozenset(), "data/activity_laps") == []


class TestLoadComponentsForBatch:
    def test_no_files_gives_an_empty_list(self) -> None:
        assert import_service._load_components_for_batch(_ctx(), [], [], "laps") == []

    def test_only_the_components_of_the_batch_are_kept(self) -> None:
        ctx = _ctx(
            {"data/activity_laps_000.json": [{"activity_id": 1, "lap_index": 1}, {"activity_id": 2, "lap_index": 1}]}
        )
        result = import_service._load_components_for_batch(
            ctx, ["data/activity_laps_000.json"], [{"id": 1}, {"id": 3}], "laps"
        )

        assert len(result) == 1
        assert result[0]["activity_id"] == 1

    def test_a_part_that_is_not_json_is_skipped(self) -> None:
        ctx = _ctx({"data/bad.json": b"not-valid-json"})
        assert import_service._load_components_for_batch(ctx, ["data/bad.json"], [{"id": 1}], "laps") == []

    def test_a_part_the_reader_cannot_read_is_skipped(self) -> None:
        ctx = _ctx({"data/laps.json": b"x" * 2048})
        with patch.object(profile_utils.ZipArchiveReader, "_read", side_effect=FileFormatError("bad format")):
            assert import_service._load_components_for_batch(ctx, ["data/laps.json"], [{"id": 1}], "laps") == []

    def test_a_memory_error_propagates(self) -> None:
        ctx = _ctx({"data/laps.json": [{"activity_id": 1}]})
        with (
            patch.object(profile_utils.ZipArchiveReader, "_read", side_effect=MemoryAllocationError("oom")),
            pytest.raises(MemoryAllocationError),
        ):
            import_service._load_components_for_batch(ctx, ["data/laps.json"], [{"id": 1}], "laps")


class TestRestoreActivityFiles:
    async def test_a_valid_file_is_stored_under_the_new_id(self) -> None:
        ctx = _ctx({"activity_files/1.gpx": b"<gpx></gpx>"})
        ctx.counts["activity_files"] = 0
        validator = MagicMock()
        validator.config.limits.max_activity_file_size = 1000000
        with (
            patch.object(import_service.file_uploads, "file_validator", validator),
            patch.object(import_service.file_uploads, "validate_bytes", new_callable=AsyncMock),
            patch.object(import_service.activity_file_storage_integration, "store_activity_file") as store,
        ):
            await import_service._restore_activity_files(ctx, {1: 10})

        assert ctx.counts["activity_files"] == 1
        store.assert_called_once_with(10, ".gpx", b"<gpx></gpx>", ctx.storage)

    async def test_the_memory_check_keeps_its_operation_name(self) -> None:
        check_memory = MagicMock()
        await import_service._restore_activity_files(_ctx(check_memory=check_memory), {})

        check_memory.assert_called_once_with("activity files import")

    async def test_a_file_without_a_mapping_is_skipped(self) -> None:
        ctx = _ctx({"activity_files/999.gpx": b"<gpx></gpx>"})
        ctx.counts["activity_files"] = 0
        with patch.object(import_service.activity_file_storage_integration, "store_activity_file") as store:
            await import_service._restore_activity_files(ctx, {1: 10})

        store.assert_not_called()
        assert ctx.counts["activity_files"] == 0

    async def test_an_invalid_file_is_dropped(self) -> None:
        ctx = _ctx({"activity_files/1.gpx": b"<gpx></gpx>"})
        ctx.counts["activity_files"] = 0
        validator = MagicMock()
        validator.config.limits.max_activity_file_size = 1000000
        with (
            patch.object(import_service.file_uploads, "file_validator", validator),
            patch.object(
                import_service.file_uploads,
                "validate_bytes",
                new_callable=AsyncMock,
                side_effect=core_exceptions.InvalidInputError("invalid file"),
            ),
            patch.object(import_service.activity_file_storage_integration, "store_activity_file") as store,
        ):
            await import_service._restore_activity_files(ctx, {1: 10})

        store.assert_not_called()
        assert ctx.counts["activity_files"] == 0

    async def test_a_file_without_a_numeric_id_is_skipped_and_logged(self) -> None:
        ctx = _ctx({"activity_files/notes.gpx": b"data"})
        with (
            patch.object(import_service.activity_file_storage_integration, "store_activity_file") as store,
            patch.object(import_service.logger, "debug") as debug,
        ):
            await import_service._restore_activity_files(ctx, {1: 2})

        store.assert_not_called()
        assert any("without an activity id" in str(call.args[0]) for call in debug.call_args_list)

    async def test_a_value_error_from_storing_is_not_swallowed(self) -> None:
        ctx = _ctx({"activity_files/1.gpx": b"data"})
        with (
            patch.object(import_service.file_uploads, "validate_bytes", new_callable=AsyncMock),
            patch.object(
                import_service.activity_file_storage_integration,
                "store_activity_file",
                side_effect=ValueError("storage rejected the key"),
            ),
            pytest.raises(ValueError, match="storage rejected"),
        ):
            await import_service._restore_activity_files(ctx, {1: 2})


class TestRestoreActivityMedia:
    async def test_a_valid_image_is_stored_under_the_new_id(self) -> None:
        storage = MagicMock()
        ctx = _ctx({"activity_media/1_photo.jpg": b"image-data"}, storage=storage)
        ctx.counts["media"] = 0
        validator = MagicMock()
        validator.config.limits.max_image_size = 1000000
        with (
            patch.object(import_service.file_uploads, "file_validator", validator),
            patch.object(import_service.file_uploads, "validate_bytes", new_callable=AsyncMock),
        ):
            await import_service._restore_activity_media(ctx, {1: 10})

        assert ctx.counts["media"] == 1
        storage.save.assert_called_once_with("activity_media", "10_photo.jpg", b"image-data")

    async def test_the_memory_check_keeps_its_operation_name(self) -> None:
        check_memory = MagicMock()
        await import_service._restore_activity_media(_ctx(check_memory=check_memory), {})

        check_memory.assert_called_once_with("activity media import")

    async def test_an_image_without_a_mapping_is_skipped(self) -> None:
        storage = MagicMock()
        ctx = _ctx({"activity_media/999_photo.jpg": b"image-data"}, storage=storage)
        ctx.counts["media"] = 0
        await import_service._restore_activity_media(ctx, {1: 10})

        storage.save.assert_not_called()
        assert ctx.counts["media"] == 0

    async def test_an_invalid_image_is_never_stored(self) -> None:
        storage = MagicMock()
        ctx = _ctx({"activity_media/1_bad.jpg": b"image-data"}, storage=storage)
        ctx.counts["media"] = 0
        validator = MagicMock()
        validator.config.limits.max_image_size = 1000000
        with (
            patch.object(import_service.file_uploads, "file_validator", validator),
            patch.object(
                import_service.file_uploads,
                "validate_bytes",
                new_callable=AsyncMock,
                side_effect=core_exceptions.InvalidInputError("invalid image"),
            ),
        ):
            await import_service._restore_activity_media(ctx, {1: 10})

        assert ctx.counts["media"] == 0
        storage.save.assert_not_called()

    async def test_an_image_without_a_numeric_id_is_skipped_and_logged(self) -> None:
        ctx = _ctx({"activity_media/abc_photo.png": b"data"})
        ctx.counts["media"] = 0
        with (
            patch.object(import_service.activity_media_integration, "store_media_blob") as store,
            patch.object(import_service.logger, "debug") as debug,
        ):
            await import_service._restore_activity_media(ctx, {1: 2})

        store.assert_not_called()
        assert ctx.counts["media"] == 0
        assert any("without an activity id" in str(call.args[0]) for call in debug.call_args_list)

    async def test_a_value_error_from_storing_is_not_swallowed(self) -> None:
        ctx = _ctx({"activity_media/1_photo.png": b"data"})
        with (
            patch.object(import_service.file_uploads, "validate_bytes", new_callable=AsyncMock),
            patch.object(
                import_service.activity_media_integration,
                "store_media_blob",
                side_effect=ValueError("storage rejected the key"),
            ),
            pytest.raises(ValueError, match="storage rejected"),
        ):
            await import_service._restore_activity_media(ctx, {1: 2})
