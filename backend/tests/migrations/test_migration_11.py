"""Tests for migration 11: local storage objects become plain files."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from jasil.backends.storage_local import LocalStorage
from sqlalchemy.orm import Session

import migrations.migration_11 as migration_11
import migrations.utils as migrations_utils
import module_registry

_MODULE = "migrations.migration_11"


def _run(tmp_path: Path, storage: LocalStorage, *, storage_uri: str = "local://"):
    db = MagicMock(spec=Session)
    with (
        patch(f"{_MODULE}.core_config") as config,
        patch(f"{_MODULE}.platform_runtime") as runtime,
        patch(f"{_MODULE}.migrations_service") as migrations_service,
        patch(f"{_MODULE}.activity_thumbnail_scheduled_jobs.schedule_full_thumbnail_regeneration") as schedule,
    ):
        config.settings.DATA_DIR = str(tmp_path)
        config.settings.resolved_storage_uri = storage_uri
        runtime.get_active_platform.return_value.storage = storage

        migration_11.process_migration_11(db)

    return db, migrations_service, schedule


class TestProcessMigration11:
    def test_is_registered_as_a_synchronous_data_migration(self):
        assert migrations_utils._SYNC_MIGRATIONS[11] is migration_11.process_migration_11

    def test_moves_hashed_objects_from_every_area_to_plain_files(self, tmp_path: Path):
        areas = module_registry.storage_plain_areas()
        old_storage = LocalStorage(str(tmp_path))
        expected: dict[tuple[str, str], bytes] = {}
        for index, area in enumerate(sorted(areas)):
            key = f"nested/{index}.blob"
            data = f"payload-{area}".encode()
            old_storage.save(area, key, data)
            expected[(area, key)] = data

        plain_storage = LocalStorage(str(tmp_path), plain_areas=areas)

        db, migrations_service, schedule = _run(tmp_path, plain_storage)

        for (area, key), data in expected.items():
            assert (tmp_path / area / key).read_bytes() == data
            assert plain_storage.get(area, key) == data
        assert list((tmp_path / ".jasil-objects").rglob("object")) == []
        migrations_service.mark_executed.assert_called_once_with(11, db)
        schedule.assert_called_once_with()

    def test_schedules_full_thumbnail_regeneration_after_local_migration(self, tmp_path: Path):
        areas = module_registry.storage_plain_areas()
        old_storage = LocalStorage(str(tmp_path))
        old_storage.save(sorted(areas)[0], "old.webp", b"thumbnail")
        storage = LocalStorage(str(tmp_path), plain_areas=areas)
        db = MagicMock(spec=Session)
        steps: list[str] = []

        with (
            patch(f"{_MODULE}.core_config") as config,
            patch(f"{_MODULE}.platform_runtime") as runtime,
            patch(f"{_MODULE}.migrations_service") as migrations_service,
            patch(f"{_MODULE}.activity_thumbnail_scheduled_jobs.schedule_full_thumbnail_regeneration") as schedule,
        ):
            config.settings.DATA_DIR = str(tmp_path)
            config.settings.resolved_storage_uri = "local://"
            runtime.get_active_platform.return_value.storage = storage
            migrations_service.mark_executed.side_effect = lambda *_: steps.append("marked")
            schedule.side_effect = lambda: steps.append("scheduled")

            migration_11.process_migration_11(db)

        schedule.assert_called_once_with()
        assert steps == ["marked", "scheduled"]

    def test_leaves_existing_plain_files_unchanged(self, tmp_path: Path):
        areas = module_registry.storage_plain_areas()
        area = sorted(areas)[0]
        destination = tmp_path / area / "already-plain.bin"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"plain")
        storage = LocalStorage(str(tmp_path), plain_areas=areas)

        with patch.object(storage, "save_stream", wraps=storage.save_stream) as save_stream:
            _, _, schedule = _run(tmp_path, storage)

        assert destination.read_bytes() == b"plain"
        save_stream.assert_not_called()
        schedule.assert_called_once_with()

    def test_skips_non_local_storage_and_marks_migration_executed(self, tmp_path: Path):
        storage = MagicMock()

        _, migrations_service, schedule = _run(tmp_path, storage, storage_uri="s3://bucket")

        storage.iter_objects.assert_not_called()
        migrations_service.mark_executed.assert_called_once()
        schedule.assert_not_called()

    def test_partial_failure_retries_without_losing_or_rewriting_objects(self, tmp_path: Path):
        areas = module_registry.storage_plain_areas()
        old_storage = LocalStorage(str(tmp_path))
        area = sorted(areas)[0]
        old_storage.save(area, "first.bin", b"first")
        old_storage.save(area, "second.bin", b"second")
        storage = LocalStorage(str(tmp_path), plain_areas=areas)
        save_stream = storage.save_stream

        def fail_second(area_name, key, source, **kwargs):
            if key == "second.bin":
                raise OSError("disk full")
            return save_stream(area_name, key, source, **kwargs)

        db = MagicMock(spec=Session)
        with (
            patch(f"{_MODULE}.core_config") as config,
            patch(f"{_MODULE}.platform_runtime") as runtime,
            patch(f"{_MODULE}.migrations_service") as migrations_service,
            patch(f"{_MODULE}.activity_thumbnail_scheduled_jobs.schedule_full_thumbnail_regeneration") as schedule,
            patch.object(storage, "save_stream", side_effect=fail_second),
        ):
            config.settings.DATA_DIR = str(tmp_path)
            config.settings.resolved_storage_uri = "local://"
            runtime.get_active_platform.return_value.storage = storage

            migration_11.process_migration_11(db)

        migrations_service.mark_executed.assert_not_called()
        schedule.assert_not_called()
        assert (tmp_path / area / "first.bin").read_bytes() == b"first"
        assert not (tmp_path / area / "second.bin").exists()
        assert storage.get(area, "second.bin") == b"second"

        _, migrations_service, schedule = _run(tmp_path, storage)

        assert (tmp_path / area / "first.bin").read_bytes() == b"first"
        assert (tmp_path / area / "second.bin").read_bytes() == b"second"
        migrations_service.mark_executed.assert_called_once()
        schedule.assert_called_once_with()
