"""A user with activities to locate, and a real reverse-geocoding service to locate them with."""

import dataclasses
from collections.abc import Callable, Iterator
from types import SimpleNamespace

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
from tests._helpers.stand_ins import GeocodingServer


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


@pytest.fixture
def paced_geocoder(geocoding_server) -> HttpGeocoding:
    """The geocoder of ``geocoder`` with one lookup per second, installed as the active platform's.

    The first lookup takes the turn it finds free; the next one finds none for a second.
    """
    platform = platform_runtime.get_active_platform()
    provider = HttpGeocoding(
        "nominatim",
        f"http://127.0.0.1:{geocoding_server.port}/reverse",
        state=platform.state,
        clock=platform.clock,
        min_interval_seconds=1,
    )
    platform_runtime.set_active_platform(dataclasses.replace(platform, geocoding=provider))
    return provider
