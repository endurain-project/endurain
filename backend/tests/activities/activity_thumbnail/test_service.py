"""Tests for the thumbnail service: resolve, generate, delete, and backfill."""

from unittest.mock import MagicMock, patch


class TestResolveTileSettings:
    @patch("modules.activities.activity_thumbnail.service.core_cryptography")
    @patch("modules.activities.activity_thumbnail.service.server_settings_crud")
    def test_with_settings_and_key(self, mock_ss, mock_crypto):
        from modules.activities.activity_thumbnail.service import resolve_tile_settings

        settings = MagicMock()
        settings.tileserver_url = "https://tiles/{z}/{x}/{y}.png"
        settings.map_background_color = "#abc"
        settings.tileserver_api_key = "enc"
        mock_ss.get_server_settings.return_value = settings
        mock_crypto.decrypt_token_fernet.return_value = "plain"

        url, background_color, api_key = resolve_tile_settings(MagicMock())

        assert url == "https://tiles/{z}/{x}/{y}.png"
        assert background_color == "#abc"
        assert api_key == "plain"
        mock_crypto.decrypt_token_fernet.assert_called_once_with("enc")

    @patch("modules.activities.activity_thumbnail.service.server_settings_crud")
    def test_defaults_without_settings(self, mock_ss):
        import modules.activities.activity_thumbnail.render as render
        from modules.activities.activity_thumbnail.service import resolve_tile_settings

        mock_ss.get_server_settings.return_value = None

        url, background_color, api_key = resolve_tile_settings(MagicMock())

        assert url == render._DEFAULT_TILE_URL
        assert background_color == render._DEFAULT_BG_COLOR
        assert api_key is None


class TestGenerateAndStoreThumbnail:
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_render")
    def test_none_when_render_skipped(self, mock_render, mock_crud):
        from modules.activities.activity_thumbnail.service import generate_and_store_thumbnail

        mock_render.render_activity_thumbnail.return_value = None
        storage = MagicMock()

        result = generate_and_store_thumbnail(
            1, [{"lat": 1.0, "lon": 2.0}], storage, MagicMock(), tile_url="u", background_color="#fff", api_key=None
        )

        assert result is None
        storage.save.assert_not_called()
        mock_crud.set_activity_thumbnail_path.assert_not_called()

    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_render")
    def test_saves_and_records_key(self, mock_render, mock_crud):
        from modules.activities.activity_thumbnail.service import generate_and_store_thumbnail

        mock_render.render_activity_thumbnail.return_value = b"data"
        mock_render.thumbnail_key.return_value = "1.webp"
        mock_render.THUMBNAIL_STORAGE_AREA = "activity_thumbnails"
        mock_render.THUMBNAIL_CONTENT_TYPE = "image/webp"
        storage = MagicMock()
        db = MagicMock()

        result = generate_and_store_thumbnail(
            1, [{"lat": 1.0, "lon": 2.0}], storage, db, tile_url="u", background_color="#fff", api_key=None
        )

        assert result == "1.webp"
        storage.save.assert_called_once_with("activity_thumbnails", "1.webp", b"data", "image/webp")
        mock_crud.set_activity_thumbnail_path.assert_called_once_with(1, "1.webp", db)


class TestDeleteActivityThumbnail:
    def test_deletes_derived_key(self):
        from modules.activities.activity_thumbnail.service import delete_activity_thumbnail

        storage = MagicMock()

        delete_activity_thumbnail(5, storage)

        storage.delete.assert_called_once_with("activity_thumbnails", "5.webp")


class TestDeleteAndRegenerateThumbnails:
    """delete_and_regenerate_all_activity_thumbnails: storage-backed deletion."""

    @patch("modules.activities.activity_thumbnail.service.generate_missing_activity_thumbnails")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_deletes_blobs_and_clears_db(self, mock_logger, mock_runtime, mock_crud, mock_session, mock_gen):
        from modules.activities.activity_thumbnail.service import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        platform = MagicMock()
        platform.storage = storage
        mock_runtime.get_active_platform.return_value = platform

        a1 = MagicMock(id=1, map_thumbnail_path="1.webp")
        a2 = MagicMock(id=2, map_thumbnail_path="2.webp")
        mock_crud.get_activities_with_thumbnail.return_value = [a1, a2]

        delete_and_regenerate_all_activity_thumbnails()

        assert storage.delete.call_count == 2
        storage.delete.assert_any_call("activity_thumbnails", "1.webp")
        storage.delete.assert_any_call("activity_thumbnails", "2.webp")
        mock_crud.clear_all_activity_thumbnail_paths.assert_called_once_with(mock_db)
        mock_gen.assert_called_once()

    @patch("modules.activities.activity_thumbnail.service.generate_missing_activity_thumbnails")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_logs_when_delete_fails(self, mock_logger, mock_runtime, mock_crud, mock_session, mock_gen):
        from modules.activities.activity_thumbnail.service import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        storage.delete.side_effect = OSError("boom")
        platform = MagicMock()
        platform.storage = storage
        mock_runtime.get_active_platform.return_value = platform

        a1 = MagicMock(id=1, map_thumbnail_path="1.webp")
        mock_crud.get_activities_with_thumbnail.return_value = [a1]

        delete_and_regenerate_all_activity_thumbnails()

        mock_logger.print_to_log.assert_any_call(
            "Thumbnail regeneration: could not delete thumbnail for activity 1: boom",
            "warning",
        )
        mock_crud.clear_all_activity_thumbnail_paths.assert_called_once()
        mock_gen.assert_called_once()


class TestGenerateMissingThumbnails:
    """generate_missing_activity_thumbnails: lock + storage-backed backfill."""

    @staticmethod
    def _platform(*, acquired=True, storage=None):
        platform = MagicMock()
        platform.lock.try_acquire.return_value.__enter__.return_value = acquired
        platform.storage = storage if storage is not None else MagicMock()
        return platform

    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_skips_when_lock_not_acquired(self, mock_logger, mock_runtime):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_runtime.get_active_platform.return_value = self._platform(acquired=False)

        generate_missing_activity_thumbnails()

        mock_logger.print_to_log.assert_any_call(
            "Thumbnail scheduler: another replica holds the backfill lock; skipping",
            "debug",
        )

    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_no_activities_without_thumbnail(self, mock_logger, mock_runtime, mock_crud, mock_session):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_runtime.get_active_platform.return_value = self._platform()
        mock_crud.get_activities_with_thumbnail.return_value = []
        mock_crud.get_activities_without_thumbnail.return_value = []

        generate_missing_activity_thumbnails()

        mock_logger.print_to_log.assert_any_call(
            "Thumbnail scheduler: no activities without thumbnail found",
            "debug",
        )

    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_clears_missing_blob_reference(self, mock_logger, mock_runtime, mock_crud, mock_session):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        storage.exists.return_value = False
        mock_runtime.get_active_platform.return_value = self._platform(storage=storage)

        activity = MagicMock(id=1, map_thumbnail_path="1.webp")
        mock_crud.get_activities_with_thumbnail.return_value = [activity]
        mock_crud.get_activities_without_thumbnail.return_value = []

        generate_missing_activity_thumbnails()

        storage.exists.assert_called_once_with("activity_thumbnails", "1.webp")
        mock_crud.set_activity_thumbnail_path.assert_called_once_with(1, None, mock_db)

    @patch("modules.activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("modules.activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.activity_streams_crud")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_generates_thumbnail_for_activity_with_gps(
        self, mock_logger, mock_runtime, mock_streams_crud, mock_crud, mock_session, mock_resolve, mock_generate
    ):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        mock_runtime.get_active_platform.return_value = self._platform(storage=storage)
        mock_crud.get_activities_with_thumbnail.return_value = []

        act = MagicMock(id=1)
        mock_crud.get_activities_without_thumbnail.return_value = [act]
        mock_resolve.return_value = ("https://tiles/{z}/{x}/{y}.png", "#fff", None)
        mock_generate.return_value = "1.webp"

        mock_streams_crud.get_gps_stream_waypoints_for_activities.return_value = {
            1: [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}]
        }

        generate_missing_activity_thumbnails()

        mock_generate.assert_called_once()
        args = mock_generate.call_args.args
        assert args[0] == 1
        assert args[2] is storage

    @patch("modules.activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("modules.activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_crud")
    @patch("modules.activities.activity_thumbnail.service.activity_streams_crud")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.core_logger")
    def test_skips_activity_without_gps_stream(
        self, mock_logger, mock_runtime, mock_streams_crud, mock_crud, mock_session, mock_resolve, mock_generate
    ):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        mock_runtime.get_active_platform.return_value = self._platform(storage=storage)
        mock_crud.get_activities_with_thumbnail.return_value = []

        act1 = MagicMock(id=1)
        act2 = MagicMock(id=2)
        mock_crud.get_activities_without_thumbnail.return_value = [act1, act2]
        mock_resolve.return_value = ("url", "#fff", None)
        mock_generate.return_value = "1.webp"

        # Only activity 1 has a GPS stream; activity 2 is skipped.
        mock_streams_crud.get_gps_stream_waypoints_for_activities.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}

        generate_missing_activity_thumbnails()

        mock_generate.assert_called_once()
