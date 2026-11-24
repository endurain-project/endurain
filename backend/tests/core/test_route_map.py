"""Tests for the SSRF-safe static route-map renderer."""

import socket
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

import core.route_map as core_route_map
from core.route_map import RouteMapRenderRequest, UnsafeTileServerError, _GuardedStaticMap, render

_TILE_HOST = "tiles.example.com"
_PUBLIC_ADDRESS = "93.184.216.34"


def _png_tile() -> bytes:
    tile = BytesIO()
    Image.new("RGB", (256, 256), "white").save(tile, "PNG")
    return tile.getvalue()


@pytest.fixture
def dns(monkeypatch):
    """Return a function that sets what the resolver answers for the tile host, counting the lookups."""
    lookups: list[str] = []

    def answer(*addresses: str) -> list[str]:
        def getaddrinfo(host, port, *args, **kwargs):
            lookups.append(host)
            if not addresses:
                raise socket.gaierror("Name or service not known")
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in addresses]

        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        return lookups

    return answer


class _TileServer:
    """The tile server the pinned connection pool dials: records the connections and answers tiles."""

    def __init__(self, body: bytes = b"tile", status: int = 200) -> None:
        self.body = body
        self.status = status
        self.pools: list[dict] = []
        self.requests: list[dict] = []
        self.closed = 0

    def pool(self, address, **kwargs):
        server = self
        server.pools.append({"address": address, **kwargs})

        class Pool:
            def request(self, method, target, **options):
                server.requests.append({"method": method, "target": target, **options})
                return SimpleNamespace(status=server.status, data=server.body)

            def close(self):
                server.closed += 1

        return Pool()


@pytest.fixture
def tile_server(monkeypatch):
    server = _TileServer(body=_png_tile())
    monkeypatch.setattr(core_route_map, "HTTPSConnectionPool", server.pool)
    return server


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
    def test_renders_a_webp_image_from_the_tiles_of_the_validated_host(self, dns, tile_server):
        dns(_PUBLIC_ADDRESS)

        data = render(_request())

        image = Image.open(BytesIO(data))
        assert image.format == "WEBP"
        assert image.size == (1200, 400)

    def test_every_tile_request_has_a_bounded_timeout(self, dns, tile_server):
        dns(_PUBLIC_ADDRESS)

        render(_request())

        assert {request["timeout"] for request in tile_server.requests} == {_request().request_timeout_seconds}

    def test_rejects_a_private_tile_target_before_rendering(self, dns, tile_server):
        dns("10.0.0.5")

        with pytest.raises(UnsafeTileServerError):
            render(_request())

        assert tile_server.pools == []

    def test_resolves_the_tile_host_once_for_every_tile_of_a_render(self, dns, tile_server):
        lookups = dns(_PUBLIC_ADDRESS)

        render(_request())

        assert len(tile_server.requests) > 1
        assert lookups == [_TILE_HOST]
        assert {pool["address"] for pool in tile_server.pools} == {_PUBLIC_ADDRESS}

    def test_names_the_host_when_it_cannot_be_resolved(self, dns, caplog):
        dns()

        with pytest.raises(UnsafeTileServerError):
            render(_request())

        assert caplog.records[-1].host == _TILE_HOST

    def test_fewer_than_two_coordinates_is_refused(self):
        request = _request()
        short = RouteMapRenderRequest(**{**request.__dict__, "coordinates": ((-9.0, 38.0),)})

        with pytest.raises(ValueError, match="two route coordinates"):
            render(short)


class TestGuardedStaticMap:
    @staticmethod
    def _map() -> _GuardedStaticMap:
        return _GuardedStaticMap(100, 100, pinned_host=_TILE_HOST, pinned_address=_PUBLIC_ADDRESS)

    def test_pins_each_request_to_the_validated_address(self, dns, tile_server):
        lookups = dns(_PUBLIC_ADDRESS)
        tile_server.body = b"tile"

        result = self._map().get(f"https://{_TILE_HOST}/1/2/3.png", timeout=10, headers={})

        assert result == (200, b"tile")
        assert lookups == []
        assert tile_server.pools == [
            {"address": _PUBLIC_ADDRESS, "port": 443, "assert_hostname": _TILE_HOST, "server_hostname": _TILE_HOST}
        ]
        assert tile_server.requests == [
            {
                "method": "GET",
                "target": "/1/2/3.png",
                "headers": {"Host": _TILE_HOST},
                "timeout": 10,
                "redirect": False,
                "retries": False,
            }
        ]
        assert tile_server.closed == 1

    def test_uses_the_shared_default_timeout_when_staticmap_omits_one(self, tile_server):
        self._map().get(f"https://{_TILE_HOST}/1/2/3.png", headers={})

        assert tile_server.requests[0]["timeout"] == _request().request_timeout_seconds

    def test_refuses_a_tile_url_on_another_host(self, tile_server):
        with pytest.raises(UnsafeTileServerError):
            self._map().get("https://other.example.com/1/2/3.png", headers={})

        assert tile_server.pools == []
