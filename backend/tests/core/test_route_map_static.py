"""Tests for the SSRF-safe static route-map renderer backend."""

from unittest.mock import MagicMock, patch

import pytest

from infra.backends.route_map_static import StaticRouteMapRenderer, UnsafeTileServerError, _GuardedStaticMap
from infra.providers import RouteMapRenderRequest


def _request() -> RouteMapRenderRequest:
    return RouteMapRenderRequest(
        coordinates=((-9.0, 38.0), (-9.1, 38.1)),
        tile_url="https://tiles.example.com/{z}/{x}/{y}.png",
        background_color="#ffffff",
        headers={"User-Agent": "Endurain"},
        width=1200,
        height=400,
        line_color="#00aa00",
        line_width=4,
        marker_outer_color="#ffffff",
        marker_outer_radius=20,
        start_color="#00ff00",
        end_color="#ff0000",
        marker_inner_radius=13,
        quality=75,
        encoder_method=6,
    )


class TestStaticRouteMapRenderer:
    @patch("infra.backends.route_map_static._GuardedStaticMap")
    @patch("infra.backends.route_map_static.core_network.url_rejection_reason", return_value=None)
    def test_renders_webp_with_a_bounded_tile_timeout(self, _mock_rejection, mock_static_map):
        image = MagicMock()
        image.save.side_effect = lambda buffer, *_args, **_kwargs: buffer.write(b"webpdata")
        mock_static_map.return_value.render.return_value = image

        data = StaticRouteMapRenderer().render(_request())

        assert data == b"webpdata"
        assert mock_static_map.call_args.kwargs["tile_request_timeout"] == 10.0
        assert image.save.call_args.args[1] == "WEBP"
        assert image.save.call_args.kwargs == {"quality": 75, "method": 6}

    @patch("infra.backends.route_map_static._GuardedStaticMap")
    @patch(
        "infra.backends.route_map_static.core_network.url_rejection_reason",
        return_value="URL resolves to a non-public address",
    )
    def test_rejects_a_private_tile_target_before_rendering(self, _mock_rejection, mock_static_map):
        with pytest.raises(UnsafeTileServerError):
            StaticRouteMapRenderer().render(_request())

        mock_static_map.assert_not_called()


class TestGuardedStaticMap:
    @patch("infra.backends.route_map_static.requests.get")
    @patch("infra.backends.route_map_static.core_network.url_rejection_reason", return_value=None)
    def test_validates_each_url_and_refuses_redirects(self, mock_rejection, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"tile"
        tile_map = _GuardedStaticMap(100, 100)

        result = tile_map.get("https://tiles.example.com/1/2/3.png", timeout=10, headers={})

        assert result == (200, b"tile")
        mock_rejection.assert_called_once_with(
            "https://tiles.example.com/1/2/3.png",
            purpose="activity_thumbnail_tile",
        )
        mock_get.assert_called_once_with(
            "https://tiles.example.com/1/2/3.png",
            allow_redirects=False,
            timeout=10,
            headers={},
        )
