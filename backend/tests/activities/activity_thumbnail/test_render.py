"""Tests for the thumbnail render + storage-addressing helpers."""

from unittest.mock import MagicMock, patch


class TestRenderActivityThumbnail:
    @patch("activities.activity_thumbnail.render.StaticMap")
    def test_returns_webp_bytes(self, mock_staticmap):
        from activities.activity_thumbnail.render import render_activity_thumbnail

        mock_map = MagicMock()
        mock_image = MagicMock()
        mock_image.save.side_effect = lambda buf, *a, **k: buf.write(b"webpdata")
        mock_map.render.return_value = mock_image
        mock_staticmap.return_value = mock_map

        data = render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="https://tiles/{z}/{x}/{y}.png",
        )

        assert data == b"webpdata"
        mock_map.render.assert_called_once()
        assert mock_image.save.call_args.args[1] == "WEBP"
        assert mock_image.save.call_args.kwargs["quality"] == 75

    def test_none_when_too_few_waypoints(self):
        from activities.activity_thumbnail.render import render_activity_thumbnail

        assert render_activity_thumbnail(1, [{"lat": 1.0, "lon": 2.0}]) is None
        assert render_activity_thumbnail(1, []) is None

    @patch("activities.activity_thumbnail.render.StaticMap")
    def test_none_for_stadia_without_key(self, mock_staticmap):
        from activities.activity_thumbnail.render import render_activity_thumbnail

        data = render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="https://tiles.stadiamaps.com/{z}/{x}/{y}.png",
        )

        assert data is None
        mock_staticmap.assert_not_called()


class TestThumbnailKeyAndUrl:
    def test_key_format(self):
        from activities.activity_thumbnail.render import thumbnail_key

        assert thumbnail_key(42) == "42.webp"

    def test_url_none_for_missing_key(self):
        from activities.activity_thumbnail.render import thumbnail_url

        assert thumbnail_url(None) is None
        assert thumbnail_url("") is None

    @patch("activities.activity_thumbnail.render.platform_runtime")
    def test_url_uses_storage_provider(self, mock_runtime):
        from activities.activity_thumbnail.render import thumbnail_url

        storage = MagicMock()
        storage.url.return_value = "https://cdn/activity_thumbnails/1.webp"
        mock_runtime.get_active_platform.return_value.storage = storage

        assert thumbnail_url("1.webp") == "https://cdn/activity_thumbnails/1.webp"
        storage.url.assert_called_once_with("activity_thumbnails", "1.webp")

    @patch("activities.activity_thumbnail.render.platform_runtime")
    def test_url_falls_back_when_platform_uninitialised(self, mock_runtime):
        from activities.activity_thumbnail.render import thumbnail_url

        mock_runtime.get_active_platform.side_effect = RuntimeError("no platform")

        assert thumbnail_url("1.webp") == "/activity_thumbnails/1.webp"
