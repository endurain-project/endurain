"""Tests for migration 9: rewrite activity media paths to storage keys."""

from unittest.mock import MagicMock, patch

_AREA = "activity_media"


def _media(media_id: int, path: str) -> MagicMock:
    return MagicMock(id=media_id, media_path=path)


def _area_dir(tmp_path):
    """Create and return the local directory the media storage area maps to."""
    area = tmp_path / _AREA
    area.mkdir(parents=True, exist_ok=True)
    return area


def _config(tmp_path, storage_uri="local://"):
    """Patch the migration's config with a data dir and storage scheme."""
    patcher = patch("migrations.migration_9.core_config")
    mock_config = patcher.start()
    mock_config.settings.DATA_DIR = str(tmp_path)
    mock_config.settings.resolved_storage_uri = storage_uri
    return patcher


class TestProcessMigration9:
    @patch("migrations.migration_9.migrations_crud")
    @patch("migrations.migration_9.activity_media_crud")
    @patch("migrations.migration_9.platform_runtime")
    def test_local_storage_rewrites_the_row_without_re_saving(self, mock_runtime, mock_crud, mock_migrations, tmp_path):
        from migrations.migration_9 import process_migration_9

        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage
        area = _area_dir(tmp_path)
        (area / "5_abc.jpg").write_bytes(b"image")
        mock_crud.get_media_with_legacy_path.side_effect = [[_media(1, str(area / "5_abc.jpg"))], []]

        patcher = _config(tmp_path)
        try:
            process_migration_9(MagicMock())
        finally:
            patcher.stop()

        # The area already resolves to this file's directory, so the bytes are
        # left alone and only the DB value changes.
        storage.save.assert_not_called()
        assert mock_crud.edit_activity_media_media_path.call_args.args[:2] == (1, "5_abc.jpg")
        mock_migrations.set_migration_as_executed.assert_called_once()

    @patch("migrations.migration_9.migrations_crud")
    @patch("migrations.migration_9.activity_media_crud")
    @patch("migrations.migration_9.platform_runtime")
    def test_object_storage_uploads_the_bytes(self, mock_runtime, mock_crud, mock_migrations, tmp_path):
        from migrations.migration_9 import process_migration_9

        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage
        area = _area_dir(tmp_path)
        (area / "5_abc.jpg").write_bytes(b"image")
        mock_crud.get_media_with_legacy_path.side_effect = [[_media(1, str(area / "5_abc.jpg"))], []]

        patcher = _config(tmp_path, storage_uri="s3://bucket")
        try:
            process_migration_9(MagicMock())
        finally:
            patcher.stop()

        storage.save.assert_called_once_with(_AREA, "5_abc.jpg", b"image")
        assert mock_crud.edit_activity_media_media_path.call_args.args[:2] == (1, "5_abc.jpg")

    @patch("migrations.migration_9.migrations_crud")
    @patch("migrations.migration_9.activity_media_crud")
    @patch("migrations.migration_9.platform_runtime")
    def test_row_with_no_file_is_dropped(self, mock_runtime, mock_crud, mock_migrations, tmp_path):
        from migrations.migration_9 import process_migration_9

        mock_runtime.get_active_platform.return_value.storage = MagicMock()
        _area_dir(tmp_path)
        mock_crud.get_media_with_legacy_path.side_effect = [[_media(1, "/gone/5_missing.jpg")], []]

        patcher = _config(tmp_path)
        try:
            process_migration_9(MagicMock())
        finally:
            patcher.stop()

        # The record can no longer resolve to anything servable.
        assert mock_crud.delete_activity_media.call_args.args[0] == 1
        mock_crud.edit_activity_media_media_path.assert_not_called()
        mock_migrations.set_migration_as_executed.assert_called_once()

    @patch("migrations.migration_9.migrations_crud")
    @patch("migrations.migration_9.activity_media_crud")
    @patch("migrations.migration_9.platform_runtime")
    def test_a_path_from_another_container_layout_resolves_by_basename(
        self, mock_runtime, mock_crud, mock_migrations, tmp_path
    ):
        """Migration 5 hard-coded an ``/app/backend/`` prefix that a host install never had."""
        from migrations.migration_9 import process_migration_9

        mock_runtime.get_active_platform.return_value.storage = MagicMock()
        area = _area_dir(tmp_path)
        (area / "5_abc.jpg").write_bytes(b"image")
        mock_crud.get_media_with_legacy_path.side_effect = [
            [_media(1, "/app/backend/data/activity_media/5_abc.jpg")],
            [],
        ]

        patcher = _config(tmp_path)
        try:
            process_migration_9(MagicMock())
        finally:
            patcher.stop()

        assert mock_crud.edit_activity_media_media_path.call_args.args[:2] == (1, "5_abc.jpg")

    @patch("migrations.migration_9.migrations_crud")
    @patch("migrations.migration_9.activity_media_crud")
    @patch("migrations.migration_9.platform_runtime")
    def test_a_failure_leaves_the_migration_pending(self, mock_runtime, mock_crud, mock_migrations, tmp_path):
        from migrations.migration_9 import process_migration_9

        mock_runtime.get_active_platform.return_value.storage = MagicMock()
        area = _area_dir(tmp_path)
        (area / "5_abc.jpg").write_bytes(b"image")
        mock_crud.get_media_with_legacy_path.side_effect = [[_media(1, str(area / "5_abc.jpg"))], []]
        mock_crud.edit_activity_media_media_path.side_effect = RuntimeError("db down")

        patcher = _config(tmp_path)
        try:
            process_migration_9(MagicMock())
        finally:
            patcher.stop()

        # Not marked executed, so it runs again on the next startup.
        mock_migrations.set_migration_as_executed.assert_not_called()

    @patch("migrations.migration_9.migrations_crud")
    @patch("migrations.migration_9.activity_media_crud")
    @patch("migrations.migration_9.platform_runtime")
    def test_no_legacy_rows_is_a_no_op(self, mock_runtime, mock_crud, mock_migrations, tmp_path):
        from migrations.migration_9 import process_migration_9

        mock_runtime.get_active_platform.return_value.storage = MagicMock()
        mock_crud.get_media_with_legacy_path.return_value = []

        patcher = _config(tmp_path)
        try:
            process_migration_9(MagicMock())
        finally:
            patcher.stop()

        mock_crud.edit_activity_media_media_path.assert_not_called()
        mock_migrations.set_migration_as_executed.assert_called_once()
