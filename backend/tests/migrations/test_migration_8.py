"""Tests for migration 8: re-encode legacy PNG thumbnails to WebP + store keys."""

from unittest.mock import MagicMock, patch


class TestProcessMigration8:
    @patch("migrations.migration_8._reencode_to_webp")
    @patch("migrations.migration_8.Path")
    @patch("migrations.migration_8.migrations_crud")
    @patch("migrations.migration_8.activities_crud")
    @patch("migrations.migration_8.activity_thumbnail_signing")
    @patch("migrations.migration_8.platform_runtime")
    @patch("migrations.migration_8.core_logger")
    def test_converts_legacy_png_to_webp_key(
        self, mock_logger, mock_runtime, mock_thumbnail, mock_crud, mock_migrations, mock_path_cls, mock_reencode
    ):
        from migrations.migration_8 import process_migration_8

        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage
        mock_thumbnail.thumbnail_key.return_value = "1.webp"
        mock_thumbnail.THUMBNAIL_STORAGE_AREA = "activity_thumbnails"
        mock_thumbnail.THUMBNAIL_CONTENT_TYPE = "image/webp"

        act = MagicMock(id=1, map_thumbnail_path="/data/activity_thumbnails/1.png")
        # First batch returns [act], second batch empty (loop terminates).
        mock_crud.get_activities_with_legacy_thumbnail_path.side_effect = [[act], []]

        source = MagicMock()
        source.is_file.return_value = True
        mock_path_cls.return_value = source
        mock_reencode.return_value = b"webp"

        db = MagicMock()
        process_migration_8(db)

        storage.save.assert_called_once_with("activity_thumbnails", "1.webp", b"webp", "image/webp")
        mock_crud.set_activity_thumbnail_path.assert_called_once_with(1, "1.webp", db)
        source.unlink.assert_called_once_with(missing_ok=True)
        mock_migrations.set_migration_as_executed.assert_called_once_with(8, db)

    @patch("migrations.migration_8._reencode_to_webp")
    @patch("migrations.migration_8.Path")
    @patch("migrations.migration_8.migrations_crud")
    @patch("migrations.migration_8.activities_crud")
    @patch("migrations.migration_8.activity_thumbnail_signing")
    @patch("migrations.migration_8.platform_runtime")
    @patch("migrations.migration_8.core_logger")
    def test_clears_path_when_file_missing(
        self, mock_logger, mock_runtime, mock_thumbnail, mock_crud, mock_migrations, mock_path_cls, mock_reencode
    ):
        from migrations.migration_8 import process_migration_8

        storage = MagicMock()
        mock_runtime.get_active_platform.return_value.storage = storage
        mock_thumbnail.thumbnail_key.return_value = "1.webp"

        act = MagicMock(id=1, map_thumbnail_path="/data/x/1.png")
        mock_crud.get_activities_with_legacy_thumbnail_path.side_effect = [[act], []]

        source = MagicMock()
        source.is_file.return_value = False
        mock_path_cls.return_value = source

        db = MagicMock()
        process_migration_8(db)

        storage.save.assert_not_called()
        mock_reencode.assert_not_called()
        mock_crud.set_activity_thumbnail_path.assert_called_once_with(1, None, db)
        mock_migrations.set_migration_as_executed.assert_called_once_with(8, db)

    @patch("migrations.migration_8.migrations_crud")
    @patch("migrations.migration_8.activities_crud")
    @patch("migrations.migration_8.platform_runtime")
    @patch("migrations.migration_8.core_logger")
    def test_marks_executed_when_nothing_to_convert(self, mock_logger, mock_runtime, mock_crud, mock_migrations):
        from migrations.migration_8 import process_migration_8

        mock_crud.get_activities_with_legacy_thumbnail_path.return_value = []

        db = MagicMock()
        process_migration_8(db)

        mock_migrations.set_migration_as_executed.assert_called_once_with(8, db)
