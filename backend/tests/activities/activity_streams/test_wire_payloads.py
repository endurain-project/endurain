"""The JSON a stream read puts on the wire, pinned per stream type.

A stored waypoint is served exactly as stored: the same keys in the same order, an integer stays an integer and
a float stays a float, a stored ``null`` stays ``null`` and a key the activity hides stays absent. The typed
waypoint schemas describe the payload in OpenAPI; they must not change a byte of it.
"""

import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.exceptions as core_exceptions
import modules.activities.activity_streams.public_router as public_router
import modules.activities.activity_streams.router as router
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.auth.dependencies as auth_deps
from modules.activities.activity_streams.constants import ActivityStreamType

_HEADERS = {"Authorization": "Bearer x"}
_TIME = "2026-06-20T08:20:00"

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


def _key(stream_type: int) -> str:
    return ActivityStreamType.from_stored(stream_type).value


def _stream(stream_type: int, waypoints: list[dict[str, Any]]) -> activity_streams_schema.ActivityStreamsRead:
    return activity_streams_schema.ActivityStreamsRead(
        id=stream_type, activity_id=9, stream_type=stream_type, stream_waypoints=waypoints
    )


def _expected(stream_type: int, waypoints: list[dict[str, Any]]) -> dict[str, Any]:
    """The stream as it has always been served, in the key order it has always had."""
    return {
        "activity_id": 9,
        "stream_type": _key(stream_type),
        "stream_waypoints": waypoints,
        "strava_activity_stream_id": None,
        "id": stream_type,
        "zone_percentages": None,
    }


def _compact(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def _app(mock_db, module, prefix: str, *, authenticated: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(module.router, prefix=prefix)
    core_exceptions.register_exception_handlers(app)
    if authenticated:
        app.dependency_overrides[auth_deps.check_scopes] = lambda: None
        app.dependency_overrides[auth_deps.get_current_user_id] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


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


@pytest.mark.parametrize(("stream_type", "stored"), _CASES)
class TestAuthenticatedRouter:
    @patch("modules.activities.activity_streams.router.activity_streams_service.get_activity_stream")
    def test_one_stream_is_served_as_stored(self, mock_get, stream_type, stored, mock_db):
        mock_get.return_value = _stream(stream_type, stored)

        response = TestClient(_app(mock_db, router, "/activities/{activity_id}", authenticated=True)).get(
            f"/activities/1/streams/{_key(stream_type)}", headers=_HEADERS
        )

        assert response.status_code == 200
        assert response.content == _compact(_expected(stream_type, stored))

    @patch("modules.activities.activity_streams.router.activity_streams_service.list_activity_streams")
    def test_a_page_of_streams_is_served_as_stored(self, mock_list, stream_type, stored, mock_db):
        mock_list.return_value = activity_streams_schema.ActivityStreamsPage.build(
            [_stream(stream_type, stored)], 1, 1, 200
        )

        response = TestClient(_app(mock_db, router, "/activities/{activity_id}", authenticated=True)).get(
            "/activities/1/streams", headers=_HEADERS
        )

        assert response.status_code == 200
        assert response.content == _compact(
            {"items": [_expected(stream_type, stored)], "total": 1, "page": 1, "num_records": 200, "next": None}
        )


@pytest.mark.parametrize(("stream_type", "stored"), _CASES)
class TestPublicRouter:
    @patch("modules.activities.activity_streams.public_router.activity_streams_service.get_public_activity_stream")
    def test_one_stream_is_served_as_stored(self, mock_get, stream_type, stored, mock_db):
        mock_get.return_value = _stream(stream_type, stored)

        response = TestClient(
            _app(mock_db, public_router, "/public/activities/{activity_id}", authenticated=False)
        ).get(f"/public/activities/1/streams/{_key(stream_type)}")

        assert response.status_code == 200
        assert response.content == _compact(_expected(stream_type, stored))


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


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(router.router, prefix="/activities/{activity_id}")
    app.include_router(public_router.router, prefix="/public/activities/{activity_id}")
    return app.openapi()


class TestOpenApi:
    @pytest.mark.parametrize("stream_type", sorted(_DESCRIBED))
    def test_each_stream_type_describes_its_waypoints(self, document, stream_type):
        stream_name, waypoint_name, keys = _DESCRIBED[stream_type]
        schemas = document["components"]["schemas"]

        stream = schemas[stream_name]
        waypoint = schemas[waypoint_name]

        assert stream["properties"]["stream_type"] == {"$ref": "#/components/schemas/ActivityStreamType"}
        assert stream["properties"]["stream_waypoints"]["items"] == {"$ref": f"#/components/schemas/{waypoint_name}"}
        assert set(waypoint["properties"]) == {"time", *keys}
        for key in keys:
            assert {"type": "number"} in waypoint["properties"][key]["anyOf"]

    def test_the_stream_type_is_one_of_the_eight_keys(self, document):
        assert document["components"]["schemas"]["ActivityStreamType"]["enum"] == [
            _key(stream_type) for stream_type in sorted(_DESCRIBED)
        ]

    def test_a_stream_is_one_of_the_typed_streams_without_a_string_keyed_mapping(self, document):
        union = document["components"]["schemas"]["ActivityStreamResponse"]

        assert [option["$ref"].rsplit("/", 1)[1] for option in union["oneOf"]] == [
            name for name, _, _ in (_DESCRIBED[stream_type] for stream_type in sorted(_DESCRIBED))
        ]
        assert "discriminator" not in union

    def test_the_routes_answer_with_the_typed_streams(self, document):
        for path in (
            "/activities/{activity_id}/streams/{stream_type}",
            "/public/activities/{activity_id}/streams/{stream_type}",
        ):
            ok = document["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
            assert ok == {"$ref": "#/components/schemas/ActivityStreamResponse"}
        page = document["components"]["schemas"]["Page_ActivityStreamResponse_"]
        assert page["properties"]["items"]["items"] == {"$ref": "#/components/schemas/ActivityStreamResponse"}
