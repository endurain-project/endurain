"""Tests for the thumbnail render + storage-addressing helpers."""

from unittest.mock import patch


class TestRenderActivityThumbnail:
    @patch("modules.activities.activity_thumbnail.render.core_route_map")
    def test_returns_webp_bytes(self, mock_route_map):
        from modules.activities.activity_thumbnail.render import render_activity_thumbnail

        mock_route_map.render.return_value = b"webpdata"

        data = render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="https://tiles/{z}/{x}/{y}.png",
        )

        assert data == b"webpdata"
        request = mock_route_map.render.call_args.args[0]
        assert request.coordinates == ((-9.0, 38.0), (-9.1, 38.1))
        assert request.tile_url == "https://tiles/{z}/{x}/{y}.png"
        assert request.quality == 75
        assert request.request_timeout_seconds == 10.0

    def test_none_when_too_few_waypoints(self):
        from modules.activities.activity_thumbnail.render import render_activity_thumbnail

        assert render_activity_thumbnail(1, [{"lat": 1.0, "lon": 2.0}]) is None
        assert render_activity_thumbnail(1, []) is None

    @patch("modules.activities.activity_thumbnail.render.core_route_map")
    def test_none_for_stadia_without_key(self, mock_route_map):
        from modules.activities.activity_thumbnail.render import render_activity_thumbnail

        data = render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="https://tiles.stadiamaps.com/{z}/{x}/{y}.png",
        )

        assert data is None
        mock_route_map.render.assert_not_called()

    @patch("modules.activities.activity_thumbnail.render.core_route_map")
    def test_sends_stadia_key_in_header_only(self, mock_route_map):
        from modules.activities.activity_thumbnail.render import render_activity_thumbnail

        mock_route_map.render.return_value = b"webpdata"

        render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="https://tiles.stadiamaps.com/{z}/{x}/{y}.png",
            api_key="secret-key",
        )

        request = mock_route_map.render.call_args.args[0]
        assert request.headers["Authorization"] == "Stadia-Auth secret-key"
        assert "secret-key" not in request.tile_url

    @patch("modules.activities.activity_thumbnail.render.core_route_map")
    def test_rejects_url_api_key_over_http(self, mock_route_map):
        from modules.activities.activity_thumbnail.render import render_activity_thumbnail

        data = render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="http://tiles.example.com/{z}/{x}/{y}.png",
            api_key="secret-key",
        )

        assert data is None
        mock_route_map.render.assert_not_called()

    @patch("modules.activities.activity_thumbnail.render.logger")
    @patch("modules.activities.activity_thumbnail.render.core_route_map")
    def test_does_not_log_secret_bearing_exception_details(self, mock_route_map, mock_logger):
        from modules.activities.activity_thumbnail.render import render_activity_thumbnail

        mock_route_map.render.side_effect = OSError("request failed: https://tiles.example.com?api_key=secret-key")

        data = render_activity_thumbnail(
            1,
            [{"lat": 38.0, "lon": -9.0}, {"lat": 38.1, "lon": -9.1}],
            tile_url="https://tiles.example.com/{z}/{x}/{y}.png",
            api_key="secret-key",
        )

        assert data is None
        warning_call = mock_logger.warning.call_args
        assert warning_call.args == ("Thumbnail generation failed",)
        assert warning_call.kwargs["extra"]["error_type"] == "OSError"
        assert "exc_info" not in warning_call.kwargs
        assert "secret-key" not in repr(warning_call)
