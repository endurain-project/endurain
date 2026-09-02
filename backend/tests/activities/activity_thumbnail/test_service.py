"""Tests for the thumbnail service: resolve, generate, delete, and backfill."""

from unittest.mock import MagicMock, patch


def _pages(*pages):
    """Return a ``side_effect`` serving each page then signalling exhaustion.

    The scan helpers read until a call comes back empty, so a plain
    ``return_value`` of a non-empty list would never terminate.

    Args:
        *pages: The pages to serve, in order.

    Returns:
        A list suitable for ``Mock.side_effect``, terminated by an empty page.
    """
    return [*[list(page) for page in pages], []]


class TestResolveTileSettings:
    """Decryption is the settings module's job; this only applies render defaults."""

    @patch("modules.activities.activity_thumbnail.service.server_settings_integration")
    def test_uses_the_configured_tile_source(self, mock_settings):
        import modules.server_settings.contracts as server_settings_contracts
        from modules.activities.activity_thumbnail.service import resolve_tile_settings

        mock_settings.get_tile_server_settings.return_value = server_settings_contracts.TileServerSettings(
            tile_url="https://tiles/{z}/{x}/{y}.png",
            background_color="#abc",
            api_key="plain",
        )

        assert resolve_tile_settings(MagicMock()) == ("https://tiles/{z}/{x}/{y}.png", "#abc", "plain")

    @patch("modules.activities.activity_thumbnail.service.server_settings_integration")
    def test_defaults_without_settings(self, mock_settings):
        import modules.activities.activity_thumbnail.render as render
        import modules.server_settings.contracts as server_settings_contracts
        from modules.activities.activity_thumbnail.service import resolve_tile_settings

        mock_settings.get_tile_server_settings.return_value = server_settings_contracts.TileServerSettings()

        url, background_color, api_key = resolve_tile_settings(MagicMock())

        assert url == render._DEFAULT_TILE_URL
        assert background_color == render._DEFAULT_BG_COLOR
        assert api_key is None


class TestGenerateAndStoreThumbnail:
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_render")
    def test_none_when_render_skipped(self, mock_render, mock_activities):
        from modules.activities.activity_thumbnail.service import generate_and_store_thumbnail

        mock_render.render_activity_thumbnail.return_value = None
        storage = MagicMock()

        result = generate_and_store_thumbnail(
            1, [{"lat": 1.0, "lon": 2.0}], storage, MagicMock(), tile_url="u", background_color="#fff", api_key=None
        )

        assert result is None
        storage.save.assert_not_called()
        mock_activities.set_thumbnail_key.assert_not_called()

    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_signing")
    @patch("modules.activities.activity_thumbnail.service.activity_thumbnail_render")
    def test_saves_and_records_key(self, mock_render, mock_signing, mock_activities):
        from modules.activities.activity_thumbnail.service import generate_and_store_thumbnail

        mock_render.render_activity_thumbnail.return_value = b"data"
        mock_signing.thumbnail_key.return_value = "1.webp"
        mock_signing.THUMBNAIL_STORAGE_AREA = "activity_thumbnails"
        mock_render.THUMBNAIL_CONTENT_TYPE = "image/webp"
        storage = MagicMock()
        db = MagicMock()

        result = generate_and_store_thumbnail(
            1, [{"lat": 1.0, "lon": 2.0}], storage, db, tile_url="u", background_color="#fff", api_key=None
        )

        assert result == "1.webp"
        storage.save.assert_called_once_with("activity_thumbnails", "1.webp", b"data", "image/webp")
        mock_activities.set_thumbnail_key.assert_called_once_with(1, "1.webp", db)


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
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_deletes_blobs_and_clears_db(self, mock_logger, mock_runtime, mock_activities, mock_session, mock_gen):
        from modules.activities.activity_thumbnail.service import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        platform = MagicMock()
        platform.storage = storage
        mock_runtime.get_active_platform.return_value = platform

        a1 = MagicMock(id=1, map_thumbnail_path="1.webp")
        a2 = MagicMock(id=2, map_thumbnail_path="2.webp")
        mock_activities.list_activities_with_thumbnail.side_effect = _pages([a1, a2])

        delete_and_regenerate_all_activity_thumbnails()

        assert storage.delete.call_count == 2
        storage.delete.assert_any_call("activity_thumbnails", "1.webp")
        storage.delete.assert_any_call("activity_thumbnails", "2.webp")
        mock_activities.clear_all_thumbnail_keys.assert_called_once_with(mock_db)
        mock_gen.assert_called_once()

    @patch("modules.activities.activity_thumbnail.service.generate_missing_activity_thumbnails")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_logs_when_delete_fails(self, mock_logger, mock_runtime, mock_activities, mock_session, mock_gen):
        from modules.activities.activity_thumbnail.service import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        storage.delete.side_effect = OSError("boom")
        platform = MagicMock()
        platform.storage = storage
        mock_runtime.get_active_platform.return_value = platform

        a1 = MagicMock(id=1, map_thumbnail_path="1.webp")
        mock_activities.list_activities_with_thumbnail.side_effect = _pages([a1])

        delete_and_regenerate_all_activity_thumbnails()

        # Structured logging: the activity and the reason are queryable fields
        # rather than interpolated into the message.
        warning = mock_logger.warning.call_args
        assert warning.args[0] == "Thumbnail regeneration: could not delete the existing thumbnail"
        assert warning.kwargs["extra"]["activity_id"] == 1
        assert warning.kwargs["extra"]["reason"] == "boom"
        mock_activities.clear_all_thumbnail_keys.assert_called_once()
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
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_skips_when_lock_not_acquired(self, mock_logger, mock_runtime):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_runtime.get_active_platform.return_value = self._platform(acquired=False)

        generate_missing_activity_thumbnails()

        mock_logger.debug.assert_any_call(
            "Thumbnail scheduler: another replica holds the backfill lock; skipping",
        )

    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_no_activities_without_thumbnail(self, mock_logger, mock_runtime, mock_activities, mock_session):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_runtime.get_active_platform.return_value = self._platform()
        mock_activities.list_activities_with_thumbnail.return_value = []
        mock_activities.list_activities_without_thumbnail.return_value = []

        generate_missing_activity_thumbnails()

        mock_logger.debug.assert_any_call(
            "Thumbnail scheduler: no activities without thumbnail found",
        )

    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_clears_missing_blob_reference(self, mock_logger, mock_runtime, mock_activities, mock_session):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        storage.exists.return_value = False
        mock_runtime.get_active_platform.return_value = self._platform(storage=storage)

        activity = MagicMock(id=1, map_thumbnail_path="1.webp")
        mock_activities.list_activities_with_thumbnail.side_effect = _pages([activity])
        mock_activities.list_activities_without_thumbnail.return_value = []

        generate_missing_activity_thumbnails()

        storage.exists.assert_called_once_with("activity_thumbnails", "1.webp")
        mock_activities.set_thumbnail_key.assert_called_once_with(1, None, mock_db)

    @patch("modules.activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("modules.activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.activity_streams_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_generates_thumbnail_for_activity_with_gps(
        self,
        mock_logger,
        mock_runtime,
        mock_streams_service,
        mock_activities,
        mock_session,
        mock_resolve,
        mock_generate,
    ):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        mock_runtime.get_active_platform.return_value = self._platform(storage=storage)
        mock_activities.list_activities_with_thumbnail.return_value = []

        act = MagicMock(id=1)
        mock_activities.list_activities_without_thumbnail.side_effect = _pages([act])
        mock_resolve.return_value = ("https://tiles/{z}/{x}/{y}.png", "#fff", None)
        mock_generate.return_value = "1.webp"

        mock_streams_service.get_gps_waypoints_for_activities.return_value = {
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
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.activity_streams_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_skips_activity_without_gps_stream(
        self,
        mock_logger,
        mock_runtime,
        mock_streams_service,
        mock_activities,
        mock_session,
        mock_resolve,
        mock_generate,
    ):
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        storage = MagicMock()
        mock_runtime.get_active_platform.return_value = self._platform(storage=storage)
        mock_activities.list_activities_with_thumbnail.return_value = []

        act1 = MagicMock(id=1)
        act2 = MagicMock(id=2)
        mock_activities.list_activities_without_thumbnail.side_effect = _pages([act1, act2])
        mock_resolve.return_value = ("url", "#fff", None)
        mock_generate.return_value = "1.webp"

        # Only activity 1 has a GPS stream; activity 2 is skipped.
        mock_streams_service.get_gps_waypoints_for_activities.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}

        generate_missing_activity_thumbnails()

        mock_generate.assert_called_once()

    @patch("modules.activities.activity_thumbnail.service.generate_and_store_thumbnail")
    @patch("modules.activities.activity_thumbnail.service.resolve_tile_settings")
    @patch("modules.activities.activity_thumbnail.service.core_database.SessionLocal")
    @patch("modules.activities.activity_thumbnail.service.activities_service")
    @patch("modules.activities.activity_thumbnail.service.activity_streams_service")
    @patch("modules.activities.activity_thumbnail.service.platform_runtime")
    @patch("modules.activities.activity_thumbnail.service.logger")
    def test_walks_every_page_advancing_the_cursor(
        self,
        mock_logger,
        mock_runtime,
        mock_streams_service,
        mock_activities,
        mock_session,
        mock_resolve,
        mock_generate,
    ):
        """The pass reads the table in bounded pages, not in one unbounded list.

        The whole activities table used to be materialised here, and each page's
        waypoints are batch-loaded, so both the paging and the per-page batching
        have to hold. A cursor that failed to advance would re-serve page one
        forever; one that skipped would silently leave activities unrendered.
        """
        from modules.activities.activity_thumbnail.service import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_runtime.get_active_platform.return_value = self._platform(storage=MagicMock())
        mock_activities.list_activities_with_thumbnail.return_value = []

        first = [MagicMock(id=1), MagicMock(id=2)]
        second = [MagicMock(id=3)]
        mock_activities.list_activities_without_thumbnail.side_effect = _pages(first, second)
        mock_resolve.return_value = ("url", "#fff", None)
        mock_generate.return_value = "x.webp"
        mock_streams_service.get_gps_waypoints_for_activities.return_value = {
            1: [{"lat": 1.0, "lon": 1.0}],
            2: [{"lat": 2.0, "lon": 2.0}],
            3: [{"lat": 3.0, "lon": 3.0}],
        }

        generate_missing_activity_thumbnails()

        # Cursor advances past the last id of each page, and stops on the empty one.
        assert [
            call.kwargs["after_id"] for call in mock_activities.list_activities_without_thumbnail.call_args_list
        ] == [
            0,
            2,
            3,
        ]
        # One waypoint batch per page, not one per activity.
        assert mock_streams_service.get_gps_waypoints_for_activities.call_count == 2
        assert mock_generate.call_count == 3
