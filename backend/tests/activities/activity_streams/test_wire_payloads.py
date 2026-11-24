"""The JSON a stream read puts on the wire, pinned per stream type, through the production application.

A stored waypoint is served exactly as stored: the same keys in the same order, an integer stays an integer and
a float stays a float, a stored ``null`` stays ``null`` and a key the activity hides stays absent. The typed
waypoint schemas describe the payload in OpenAPI; they must not change a byte of it.
"""

import json
from typing import Any

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from modules.activities.activity_streams.constants import ActivityStreamType
from tests._factories.activities import make_activity, make_stream
from tests._factories.users import make_user

_TIME = "2026-06-20T08:20:00"
_ROOT = core_config.ROOT_PATH

# stream_type -> the waypoints as the writers store them.
_STORED: dict[int, list[dict[str, Any]]] = {
    1: [{"time": _TIME, "hr": 120}, {"time": "2026-06-20T08:20:01", "hr": 0}],
    2: [{"time": _TIME, "power": 250.5}, {"time": "2026-06-20T08:20:01", "power": 300}],
    3: [{"time": _TIME, "cad": 85}, {"time": "2026-06-20T08:20:01", "cad": 86.0}],
    4: [{"time": _TIME, "ele": 1250.0}, {"time": "2026-06-20T08:20:01", "ele": 1250.25}],
    5: [{"time": _TIME, "vel": 3.5}, {"time": "2026-06-20T08:20:01", "vel": 0}],
    6: [{"time": _TIME, "pace": 0.2857142857142857}, {"time": "2026-06-20T08:20:01", "pace": 0}],
    7: [{"time": _TIME, "lat": 38.7223, "lon": -9.1393}, {"time": "2026-06-20T08:20:01", "lat": 38.72, "lon": -9.14}],
    8: [{"time": _TIME, "temp": 21.5}, {"time": "2026-06-20T08:20:01", "temp": 22}],
}
# Strava stores the offset in seconds from the start as the sample time.
_STRAVA_TIMES: dict[int, list[dict[str, Any]]] = {
    1: [{"time": 0, "hr": 120}, {"time": 1, "hr": 121}],
    7: [{"time": 0.5, "lat": 38.7, "lon": -9.1}],
}
_NULL_VALUES: dict[int, list[dict[str, Any]]] = {
    1: [{"time": _TIME, "hr": None}, {"time": "2026-06-20T08:20:01", "hr": 130}],
    4: [{"time": _TIME, "ele": None}],
}
_WITHOUT_TIME: dict[int, list[dict[str, Any]]] = {
    1: [{"hr": 120}, {"hr": 121}],
    7: [{"lat": 38.7223, "lon": -9.1393}],
}

_CASES = [
    pytest.param(stream_type, stored, id=f"{name}-{stream_type}")
    for name, payloads in (
        ("stored", _STORED),
        ("strava-times", _STRAVA_TIMES),
        ("null-values", _NULL_VALUES),
        ("hidden-time", _WITHOUT_TIME),
    )
    for stream_type, stored in payloads.items()
]


def _key(stream_type: int) -> str:
    return ActivityStreamType.from_stored(stream_type).value


def _expected(stream, waypoints: list[dict[str, Any]]) -> dict[str, Any]:
    """The stream as it has always been served, in the key order it has always had."""
    return {
        "activity_id": str(stream.activity_id),
        "stream_type": _key(stream.stream_type),
        "stream_waypoints": waypoints,
        "strava_activity_stream_id": None,
        "id": str(stream.id),
        "zone_percentages": None,
    }


def _compact(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


@pytest.fixture
def owner(committed_sessions):
    """A user with no max heart rate and no birthdate, so no zone breakdown is added to a heart-rate stream."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        db.commit()
    return user


@pytest.fixture
def stream_of(committed_sessions, owner):
    """Return a function that commits a stream of one type on a public activity and returns the stored stream."""

    def make(stream_type: int, stored: list[dict[str, Any]]):
        with committed_sessions() as db:
            activity = make_activity(db, owner.id, visibility=activity_constants.ActivityVisibility.PUBLIC)
            stream = make_stream(db, activity, stream_type, stored)
            db.commit()
        return activity, stream

    return make


@pytest.mark.parametrize(("stream_type", "stored"), _CASES)
class TestAuthenticatedRouter:
    def test_one_stream_is_served_as_stored(self, sign_in, owner, stream_of, stream_type, stored):
        activity, stream = stream_of(stream_type, stored)

        response = sign_in(owner).client.get(f"{_ROOT}/activities/{activity.id}/streams/{_key(stream_type)}")

        assert response.status_code == 200
        assert response.content == _compact(_expected(stream, stored))

    def test_a_page_of_streams_is_served_as_stored(self, sign_in, owner, stream_of, stream_type, stored):
        activity, stream = stream_of(stream_type, stored)

        response = sign_in(owner).client.get(f"{_ROOT}/activities/{activity.id}/streams")

        assert response.status_code == 200
        assert response.content == _compact(
            {"items": [_expected(stream, stored)], "total": 1, "page": 1, "num_records": 200, "next": None}
        )


@pytest.mark.usefixtures("public_links")
@pytest.mark.parametrize(("stream_type", "stored"), _CASES)
class TestPublicRouter:
    def test_one_stream_is_served_as_stored(self, client, stream_of, stream_type, stored):
        activity, stream = stream_of(stream_type, stored)

        response = client.get(f"{_ROOT}/public/activities/{activity.id}/streams/{_key(stream_type)}")

        assert response.status_code == 200
        assert response.content == _compact(_expected(stream, stored))


# stream_type -> (the stream schema, the waypoint schema, the value keys it describes)
_DESCRIBED = {
    1: ("HeartRateStreamRead", "HeartRateWaypoint", {"hr"}),
    2: ("PowerStreamRead", "PowerWaypoint", {"power"}),
    3: ("CadenceStreamRead", "CadenceWaypoint", {"cad"}),
    4: ("ElevationStreamRead", "ElevationWaypoint", {"ele"}),
    5: ("SpeedStreamRead", "SpeedWaypoint", {"vel"}),
    6: ("PaceStreamRead", "PaceWaypoint", {"pace"}),
    7: ("MapStreamRead", "MapWaypoint", {"lat", "lon"}),
    8: ("TemperatureStreamRead", "TemperatureWaypoint", {"temp"}),
}


class TestOpenApi:
    def test_each_stream_type_describes_its_waypoints(self, app):
        schemas = app.openapi()["components"]["schemas"]

        for stream_type, (stream_name, waypoint_name, keys) in _DESCRIBED.items():
            stream = schemas[stream_name]
            waypoint = schemas[waypoint_name]
            assert stream["properties"]["stream_type"] == {"$ref": "#/components/schemas/ActivityStreamType"}
            assert stream["properties"]["stream_waypoints"]["items"] == {
                "$ref": f"#/components/schemas/{waypoint_name}"
            }, stream_type
            assert set(waypoint["properties"]) == {"time", *keys}
            for key in keys:
                assert {"type": "number"} in waypoint["properties"][key]["anyOf"]

    def test_the_stream_type_is_one_of_the_eight_keys(self, app):
        schemas = app.openapi()["components"]["schemas"]

        assert schemas["ActivityStreamType"]["enum"] == [_key(stream_type) for stream_type in sorted(_DESCRIBED)]

    def test_a_stream_is_one_of_the_typed_streams_without_a_string_keyed_mapping(self, app):
        union = app.openapi()["components"]["schemas"]["ActivityStreamResponse"]

        assert [option["$ref"].rsplit("/", 1)[1] for option in union["oneOf"]] == [
            _DESCRIBED[stream_type][0] for stream_type in sorted(_DESCRIBED)
        ]
        assert "discriminator" not in union

    def test_the_routes_answer_with_the_typed_streams(self, app):
        document = app.openapi()

        for path in (
            f"{_ROOT}/activities/{{activity_id}}/streams/{{stream_type}}",
            f"{_ROOT}/public/activities/{{activity_id}}/streams/{{stream_type}}",
        ):
            ok = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            assert ok == {"$ref": "#/components/schemas/ActivityStreamResponse"}
        page = document["components"]["schemas"]["Page_ActivityStreamResponse_"]
        assert page["properties"]["items"]["items"] == {"$ref": "#/components/schemas/ActivityStreamResponse"}
