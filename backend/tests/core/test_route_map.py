"""Tests for the SSRF-safe static route-map renderer."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.route_map import RouteMapRenderRequest, UnsafeTileServerError, _GuardedStaticMap, render


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


class TestRenderRouteMap:
    @patch("core.route_map._GuardedStaticMap")
    @patch(
        "core.route_map.core_network.resolve_url_addresses",
        return_value=(("203.0.113.10",), None),
    )
    def test_renders_webp_with_a_bounded_tile_timeout(self, _mock_rejection, mock_static_map):
        image = MagicMock()
        image.save.side_effect = lambda buffer, *_args, **_kwargs: buffer.write(b"webpdata")
        mock_static_map.return_value.render.return_value = image

        data = render(_request())

        assert data == b"webpdata"
        assert mock_static_map.call_args.kwargs["tile_request_timeout"] == 10.0
        assert image.save.call_args.args[1] == "WEBP"
        assert image.save.call_args.kwargs == {"quality": 75, "method": 6}

    @patch("core.route_map._GuardedStaticMap")
    @patch(
        "core.route_map.core_network.resolve_url_addresses",
        return_value=((), "URL resolves to a non-public address"),
    )
    def test_rejects_a_private_tile_target_before_rendering(self, _mock_rejection, mock_static_map):
        with pytest.raises(UnsafeTileServerError):
            render(_request())

        mock_static_map.assert_not_called()

    @patch("core.route_map._pinned_get")
    @patch(
        "core.route_map.core_network.resolve_url_addresses",
        return_value=(("203.0.113.10",), None),
    )
    def test_resolves_the_tile_host_once_for_every_tile_of_a_render(self, mock_resolve, mock_get):
        tile = BytesIO()
        Image.new("RGB", (256, 256), "white").save(tile, "PNG")
        mock_get.return_value = (200, tile.getvalue())

        render(_request())

        assert mock_get.call_count > 1
        mock_resolve.assert_called_once()
        assert {call.args[1] for call in mock_get.call_args_list} == {"203.0.113.10"}

    @patch(
        "core.route_map.core_network.resolve_url_addresses",
        return_value=((), "URL hostname could not be resolved"),
    )
    def test_names_the_host_when_it_cannot_be_resolved(self, _mock_resolve, caplog):
        with pytest.raises(UnsafeTileServerError):
            render(_request())

        assert caplog.records[-1].host == "tiles.example.com"


class TestGuardedStaticMap:
    @patch("core.route_map.HTTPSConnectionPool")
    @patch("core.route_map.core_network.resolve_url_addresses")
    def test_pins_each_request_to_the_validated_address(self, mock_resolve, mock_pool):
        mock_pool.return_value.request.return_value.status = 200
        mock_pool.return_value.request.return_value.data = b"tile"
        tile_map = _GuardedStaticMap(100, 100, pinned_host="tiles.example.com", pinned_address="203.0.113.10")

        result = tile_map.get("https://tiles.example.com/1/2/3.png", timeout=10, headers={})

        assert result == (200, b"tile")
        mock_resolve.assert_not_called()
        mock_pool.assert_called_once_with(
            "203.0.113.10",
            port=443,
            assert_hostname="tiles.example.com",
            server_hostname="tiles.example.com",
        )
        mock_pool.return_value.request.assert_called_once_with(
            "GET",
            "/1/2/3.png",
            headers={"Host": "tiles.example.com"},
            timeout=10,
            redirect=False,
            retries=False,
        )
        mock_pool.return_value.close.assert_called_once_with()

    @patch("core.route_map.HTTPSConnectionPool")
    def test_uses_the_shared_default_timeout_when_staticmap_omits_one(self, mock_pool):
        mock_pool.return_value.request.return_value.status = 200
        mock_pool.return_value.request.return_value.data = b"tile"

        tile_map = _GuardedStaticMap(100, 100, pinned_host="tiles.example.com", pinned_address="203.0.113.10")
        tile_map.get("https://tiles.example.com/1/2/3.png", headers={})

        assert mock_pool.return_value.request.call_args.kwargs["timeout"] == _request().request_timeout_seconds

    @patch("core.route_map.HTTPSConnectionPool")
    def test_refuses_a_tile_url_on_another_host(self, mock_pool):
        tile_map = _GuardedStaticMap(100, 100, pinned_host="tiles.example.com", pinned_address="203.0.113.10")

        with pytest.raises(UnsafeTileServerError):
            tile_map.get("https://other.example.com/1/2/3.png", headers={})

        mock_pool.assert_not_called()
