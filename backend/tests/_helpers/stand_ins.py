"""Loopback stand-ins for the public map-tile and reverse-geocoding services, for tests that render or locate."""

import io
import json
import ssl
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from PIL import Image


class TileServer:
    """A real HTTP tile server on the loopback interface, answering every tile with a small PNG.

    Attributes:
        port: The port it listens on.
        status: The status every tile request is answered with.
        requests: ``(path, headers)`` of each request, in arrival order.
        on_request: Called with the request path before the answer, for a test that changes the world mid-render.
    """

    def __init__(self, tls: ssl.SSLContext | None = None) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (256, 256), (180, 200, 220)).save(buffer, "PNG")
        self._tile = buffer.getvalue()
        self.status = 200
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.on_request: Callable[[str], None] | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                if outer.on_request is not None:
                    outer.on_request(self.path)
                self.send_response(outer.status)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(outer._tile)))
                self.end_headers()
                self.wfile.write(outer._tile)

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.scheme = "http"
        if tls is not None:
            self._server.socket = tls.wrap_socket(self._server.socket, server_side=True)
            self.scheme = "https"
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def url(self, host: str = "127.0.0.1") -> str:
        """Return the tile URL template of this server under a host name."""
        return f"{self.scheme}://{host}:{self.port}/{{z}}/{{x}}/{{y}}.png"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


#: What the fake geocoder answers, by the whole degrees of the latitude asked about.
_PLACES = {
    38: {"address": {"city": "Lisbon", "suburb": "Alvalade", "country": "Portugal", "country_code": "pt"}},
    41: {"address": {"town": "Matosinhos", "country": "Portugal", "country_code": "pt"}},
}


class GeocodingServer:
    """A real HTTP reverse-geocoding service on the loopback interface, speaking Nominatim's wire format.

    Attributes:
        mode: ``"ok"`` answers a place for latitudes 38 and 41 and nothing for the rest; ``"rate_limited"`` answers
            429 with a ``Retry-After``; ``"broken"`` answers 500.
        requests: The query of each request, in arrival order.
        on_request: Called before the answer, for a test that changes the world while the lookup is in flight.
    """

    def __init__(self) -> None:
        self.mode = "ok"
        self.requests: list[dict[str, str]] = []
        self.on_request: Callable[[], None] | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
                outer.requests.append(query)
                if outer.on_request is not None:
                    outer.on_request()
                if outer.mode == "rate_limited":
                    self._answer(429, b"slow down", {"Retry-After": "120"})
                elif outer.mode == "broken":
                    self._answer(500, b"broken")
                else:
                    place = _PLACES.get(int(float(query["lat"])), {"error": "Unable to geocode"})
                    self._answer(200, json.dumps(place).encode(), {"Content-Type": "application/json"})

            def _answer(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
