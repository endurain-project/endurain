"""Tests for migration 10: user photo paths become storage keys."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

import migrations.migration_10 as migration_10

_MODULE = "migrations.migration_10"


def _run(tmp_path: Path, rows, *, storage_uri: str = "local://"):
    db = MagicMock(spec=Session)
    storage = MagicMock()

    with (
        patch(f"{_MODULE}.core_config") as config,
        patch(f"{_MODULE}.platform_runtime") as runtime,
        patch(f"{_MODULE}.users_crud") as crud,
        patch(f"{_MODULE}.migrations_crud") as migrations_crud,
    ):
        config.settings.DATA_DIR = str(tmp_path)
        config.settings.resolved_storage_uri = storage_uri
        runtime.get_active_platform.return_value.storage = storage
        crud.get_stored_photo_keys.return_value = rows

        migration_10.process_migration_10(db)

    return crud, storage, migrations_crud


class TestProcessMigration10:
    def test_rewrites_a_legacy_path_to_a_bare_key(self, tmp_path: Path):
        area = tmp_path / "user_images"
        area.mkdir()
        (area / "7.jpg").write_bytes(b"photo")

        crud, storage, migrations_crud = _run(tmp_path, [(7, "/app/backend/data/user_images/7.jpg")])

        crud.set_user_photo_key.assert_called_once()
        assert crud.set_user_photo_key.call_args.args[:2] == (7, "7.jpg")
        # Local storage already maps the area to this directory, so nothing is copied.
        storage.save.assert_not_called()
        migrations_crud.set_migration_as_executed.assert_called_once()

    def test_uploads_the_bytes_when_storage_is_remote(self, tmp_path: Path):
        area = tmp_path / "user_images"
        area.mkdir()
        (area / "7.jpg").write_bytes(b"photo")

        _, storage, _ = _run(tmp_path, [(7, "data/user_images/7.jpg")], storage_uri="s3://bucket")

        storage.save.assert_called_once_with("user_images", "7.jpg", b"photo")

    def test_clears_a_reference_with_no_file(self, tmp_path: Path):
        (tmp_path / "user_images").mkdir()

        crud, _, _ = _run(tmp_path, [(7, "data/user_images/7.jpg")])

        assert crud.set_user_photo_key.call_args.args[:2] == (7, None)

    def test_is_idempotent_for_rows_already_holding_a_key(self, tmp_path: Path):
        area = tmp_path / "user_images"
        area.mkdir()
        (area / "7.jpg").write_bytes(b"photo")

        crud, storage, _ = _run(tmp_path, [(7, "7.jpg")])

        crud.set_user_photo_key.assert_not_called()
        storage.save.assert_not_called()

    def test_skips_users_without_a_photo(self, tmp_path: Path):
        crud, _, _ = _run(tmp_path, [(7, None), (8, "")])

        crud.set_user_photo_key.assert_not_called()

    def test_a_path_escaping_the_area_is_not_migrated(self, tmp_path: Path):
        """A crafted row must not pull an arbitrary file into the photo area."""
        (tmp_path / "user_images").mkdir()
        secret = tmp_path / "secret.jpg"
        secret.write_bytes(b"not-a-photo")

        crud, _, _ = _run(tmp_path, [(7, "../secret.jpg")])

        assert crud.set_user_photo_key.call_args.args[:2] == (7, None)

    def test_a_failure_leaves_the_migration_unexecuted(self, tmp_path: Path):
        area = tmp_path / "user_images"
        area.mkdir()
        (area / "7.jpg").write_bytes(b"photo")

        db = MagicMock(spec=Session)
        with (
            patch(f"{_MODULE}.core_config") as config,
            patch(f"{_MODULE}.platform_runtime"),
            patch(f"{_MODULE}.users_crud") as crud,
            patch(f"{_MODULE}.migrations_crud") as migrations_crud,
        ):
            config.settings.DATA_DIR = str(tmp_path)
            config.settings.resolved_storage_uri = "local://"
            crud.get_stored_photo_keys.return_value = [(7, "data/user_images/7.jpg")]
            crud.set_user_photo_key.side_effect = RuntimeError("db down")

            migration_10.process_migration_10(db)

        migrations_crud.set_migration_as_executed.assert_not_called()

    def test_a_fetch_failure_aborts_without_marking_executed(self, tmp_path: Path):
        db = MagicMock(spec=Session)
        with (
            patch(f"{_MODULE}.core_config") as config,
            patch(f"{_MODULE}.platform_runtime"),
            patch(f"{_MODULE}.users_crud") as crud,
            patch(f"{_MODULE}.migrations_crud") as migrations_crud,
        ):
            config.settings.DATA_DIR = str(tmp_path)
            config.settings.resolved_storage_uri = "local://"
            crud.get_stored_photo_keys.side_effect = RuntimeError("db down")

            migration_10.process_migration_10(db)

        migrations_crud.set_migration_as_executed.assert_not_called()
