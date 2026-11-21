"""A user with activities to locate, and a real reverse-geocoding service to locate them with."""

import dataclasses
import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jasil.runtime as platform_runtime
import pytest
from jasil.backends.geocoding_http import HttpGeocoding

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema
from tests._factories.activities import make_activity
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user


@pytest.fixture
def people(committed_sessions):
    """An owner, an accepted follower of the owner and a stranger, committed."""
    with committed_sessions() as db:
        owner = make_user(db, timezone="UTC")
        follower = make_user(db, timezone="UTC")
        stranger = make_user(db, timezone="UTC")
        make_follow(db, follower.id, owner.id, accepted=True)
        db.commit()
    return SimpleNamespace(owner=owner, follower=follower, stranger=stranger)


@pytest.fixture
def make_owned_activity(committed_sessions, people) -> Callable[..., activity_schema.ActivityRead]:
    """Return a function that commits one of the owner's activities, with the children its ``stage`` callable adds."""

    def make(
        visibility: activity_constants.ActivityVisibility = activity_constants.ActivityVisibility.PRIVATE,
        stage: Callable[..., object] | None = None,
        **overrides: object,
    ) -> activity_schema.ActivityRead:
        with committed_sessions() as db:
            activity = make_activity(db, people.owner.id, visibility=visibility, **overrides)
            if stage is not None:
                stage(db, activity)
            db.commit()
        return activity

    return make


@pytest.fixture
def public_links(committed_sessions) -> None:
    """Turn public shareable links on for the server."""
    with committed_sessions() as db:
        edit_server_settings(db, public_shareable_links=True)
        db.commit()


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


@pytest.fixture
def geocoding_server(monkeypatch) -> Iterator[GeocodingServer]:
    """A loopback geocoding service the outbound-network policy allows."""
    server = GeocodingServer()
    monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.0/8"])
    yield server
    server.stop()


@pytest.fixture
def geocoder(geocoding_server) -> HttpGeocoding:
    """The platform's HTTP geocoding backend pointed at the loopback service, installed as the active platform's.

    The backend, its rate gate and its egress checks are the real ones; only the upstream is ours.
    """
    platform = platform_runtime.get_active_platform()
    provider = HttpGeocoding(
        "nominatim",
        f"http://127.0.0.1:{geocoding_server.port}/reverse",
        state=platform.state,
        clock=platform.clock,
        min_interval_seconds=0,
    )
    platform_runtime.set_active_platform(dataclasses.replace(platform, geocoding=provider))
    return provider
