"""The JSON a streams read puts on the wire and how OpenAPI describes it, through the production application."""

import json

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_activity, make_samples
from tests._factories.users import make_user

_ROOT = core_config.ROOT_PATH
_CHANNELS = ("latitude", "longitude", "elevation", "heart_rate", "power", "cadence", "speed", "pace", "temperature")


@pytest.fixture
def owner(committed_sessions):
    """A user with no max heart rate and no birthdate, so no zone breakdown is added."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        db.commit()
    return user


@pytest.fixture
def activity_of(committed_sessions, owner):
    """Return a function that commits a public activity with the given samples."""

    def make(offsets_ms, **channels):
        with committed_sessions() as db:
            activity = make_activity(db, owner.id, visibility=activity_constants.ActivityVisibility.PUBLIC)
            make_samples(db, activity, offsets_ms, **channels)
            db.commit()
        return activity

    return make


def _compact(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _expected(offsets_ms, **channels) -> dict:
    """The body in the key order it is served in: the timeline, the channels, then the zones."""
    return {"offsets_ms": offsets_ms, **{name: channels.get(name) for name in _CHANNELS}, "heart_rate_zones": None}


class TestWire:
    def test_the_body_is_served_with_its_nulls_and_in_its_documented_order(self, sign_in, owner, activity_of):
        activity = activity_of(
            [0, 500, 1000],
            heart_rate=[120.0, None, 125.0],
            speed=[4.0, 0.0, None],
            latitude=[38.5, None, 38.75],
            longitude=[-9.5, None, -9.25],
        )

        response = sign_in(owner).client.get(f"{_ROOT}/activities/{activity.id}/streams")

        assert response.status_code == 200
        assert response.content == _compact(
            _expected(
                [0, 500, 1000],
                heart_rate=[120.0, None, 125.0],
                speed=[4.0, 0.0, None],
                pace=[0.25, None, None],
                latitude=[38.5, None, 38.75],
                longitude=[-9.5, None, -9.25],
            )
        )

    @pytest.mark.usefixtures("public_links")
    def test_the_public_body_has_the_same_shape(self, client, activity_of):
        activity = activity_of([0, 1000], power=[200.0, 210.0])

        response = client.get(f"{_ROOT}/public/activities/{activity.id}/streams")

        assert response.content == _compact(_expected([0, 1000], power=[200.0, 210.0]))


class TestOpenApi:
    _PATHS = (f"{_ROOT}/activities/{{activity_id}}/streams", f"{_ROOT}/public/activities/{{activity_id}}/streams")

    def test_both_routes_answer_with_the_samples_object(self, app):
        document = app.openapi()

        for path in self._PATHS:
            ok = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            assert ok == {"$ref": "#/components/schemas/ActivitySamplesRead"}

    def test_the_per_type_routes_and_models_are_gone(self, app):
        document = app.openapi()

        assert not [path for path in document["paths"] if "/streams/" in path]
        assert not {"ActivityStreamResponse", "HeartRateStreamRead", "HeartRateWaypoint", "ActivityStreamType"} & set(
            document["components"]["schemas"]
        )

    def test_every_channel_is_a_required_nullable_list_that_states_its_unit(self, app):
        schema = app.openapi()["components"]["schemas"]["ActivitySamplesRead"]

        assert set(schema["required"]) == {"offsets_ms", "heart_rate_zones", *_CHANNELS}
        for name in _CHANNELS:
            assert {"type": "null"} in schema["properties"][name]["anyOf"]
            assert "per sample" in schema["properties"][name]["description"]
        assert "milliseconds" in schema["properties"]["offsets_ms"]["description"]

    def test_max_points_is_an_optional_bounded_integer_on_both_routes(self, app):
        document = app.openapi()

        for path in self._PATHS:
            (parameter,) = [p for p in document["paths"][path]["get"]["parameters"] if p["name"] == "max_points"]
            integer = next(option for option in parameter["schema"]["anyOf"] if option.get("type") == "integer")
            assert (parameter["required"], integer["minimum"], integer["maximum"]) == (False, 2, 10000)
