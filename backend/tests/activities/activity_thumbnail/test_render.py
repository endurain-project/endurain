"""The thumbnail renderer against a real HTTP tile server: what it asks for, what it sends and what it draws."""

import io
import uuid

import pytest
from PIL import Image

import core.config as core_config
import core.exceptions as core_exceptions
import modules.activities.activity_thumbnail.render as thumbnail_render

_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_ROUTE = [{"lat": 38.70, "lon": -9.10}, {"lat": 38.72, "lon": -9.14}]


def _render(tile_url: str, **kwargs):
    return thumbnail_render.render_activity_thumbnail(_ID, _ROUTE, tile_url=tile_url, **kwargs)


class TestRender:
    def test_the_route_is_drawn_over_the_served_tiles_as_a_webp_of_the_thumbnail_size(self, tile_server):
        data = _render(tile_server.url(), user_agent="Endurain test")

        with Image.open(io.BytesIO(data)) as image:
            assert (image.format, image.size) == ("WEBP", (1200, 400))
        assert tile_server.requests
        assert {headers["user-agent"] for _, headers in tile_server.requests} == {"Endurain test"}

    def test_the_tiles_are_asked_for_by_zoom_column_and_row(self, tile_server):
        _render(tile_server.url())

        paths = [path for path, _ in tile_server.requests]
        assert all(len(path.strip("/").split("/")) == 3 and path.endswith(".png") for path in paths)

    def test_a_route_with_fewer_than_two_points_renders_nothing_and_asks_for_nothing(self, tile_server):
        for waypoints in ([], [{"lat": 1.0, "lon": 2.0}]):
            assert thumbnail_render.render_activity_thumbnail(_ID, waypoints, tile_url=tile_server.url()) is None

        assert tile_server.requests == []

    def test_a_stadia_url_without_a_key_renders_nothing_and_asks_for_nothing(self, tile_server):
        assert _render(tile_server.url("tiles.stadiamaps.com")) is None

        assert tile_server.requests == []

    def test_a_stadia_key_travels_in_the_authorization_header_and_never_in_the_url(self, tile_server):
        assert _render(tile_server.url("tiles.stadiamaps.com"), api_key="secret-key") is not None

        assert {headers["authorization"] for _, headers in tile_server.requests} == {"Stadia-Auth secret-key"}
        assert not any("secret-key" in path for path, _ in tile_server.requests)

    @pytest.mark.parametrize("host", ["notstadiamaps.com", "tiles.example.test"])
    def test_a_lookalike_host_gets_no_stadia_authorization_and_renders_without_a_key(self, tile_server, host):
        assert _render(tile_server.url(host)) is not None

        assert all("authorization" not in headers for _, headers in tile_server.requests)

    def test_a_key_for_another_provider_is_refused_over_plain_http_and_asks_for_nothing(self, tile_server):
        assert _render(tile_server.url("tiles.example.test"), api_key="secret-key") is None

        assert tile_server.requests == []

    def test_a_key_for_another_provider_travels_in_the_query_over_https(self, tls_tile_server):
        data = _render(tls_tile_server.url("tiles.example.test"), api_key="secret-key")

        assert data is not None
        assert {path.partition("?")[2] for path, _ in tls_tile_server.requests} == {"api_key=secret-key"}
        assert all("authorization" not in headers for _, headers in tls_tile_server.requests)

    def test_a_key_is_appended_after_an_existing_query_with_an_ampersand(self, tls_tile_server):
        url = tls_tile_server.url("tiles.example.test").replace(".png", ".png?style=day")

        assert _render(url, api_key="secret-key") is not None

        assert {path.partition("?")[2] for path, _ in tls_tile_server.requests} == {"style=day&api_key=secret-key"}

    def test_a_tile_server_that_fails_is_a_processing_error_that_leaves_no_key_behind(self, tile_server):
        tile_server.status = 500

        with pytest.raises(core_exceptions.ProcessingError) as raised:
            _render(tile_server.url("tiles.stadiamaps.com"), api_key="secret-key")

        assert raised.value.__cause__ is None and raised.value.__suppress_context__ is True
        assert "secret-key" not in repr(raised.value)

    def test_a_tile_host_the_network_policy_refuses_is_a_processing_error_and_is_never_dialled(
        self, tile_server, monkeypatch
    ):
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])

        with pytest.raises(core_exceptions.ProcessingError):
            _render(tile_server.url())

        assert tile_server.requests == []

    def test_a_waypoint_without_a_coordinate_is_a_processing_error(self, tile_server):
        with pytest.raises(core_exceptions.ProcessingError):
            thumbnail_render.render_activity_thumbnail(
                _ID, [{"lat": 1.0, "lon": 2.0}, {"lat": 1.0}], tile_url=tile_server.url()
            )

    def test_a_url_template_with_other_placeholders_still_renders(self, tile_server):
        url = tile_server.url().replace("{z}/", "{s}/{z}/").replace(".png", "{r}.png")

        assert _render(url) is not None
