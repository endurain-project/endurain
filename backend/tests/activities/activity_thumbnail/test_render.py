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
