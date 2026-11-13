"""``UuidId`` accepts only a UUID as a path id."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions


@pytest.fixture
def app():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.get("/uuid-things/{thing_id}")
    def read_uuid_thing(thing_id: core_dependencies.UuidId):
        return {"id": str(thing_id)}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_a_valid_uuid_round_trips(client):
    thing_id = uuid.uuid4()

    assert client.get(f"/uuid-things/{thing_id}").json() == {"id": str(thing_id)}


@pytest.mark.parametrize("thing_id", ["abc", "1", "0123456789abcdef0123456789abcde"])
def test_a_malformed_uuid_is_a_validation_failure(client, thing_id):
    response = client.get(f"/uuid-things/{thing_id}")

    assert response.status_code == 422
    assert response.json()["type"] == "urn:endurain:error:validation-failed"


def test_a_uuid_path_parameter_is_published_as_a_uuid_string(app):
    parameter = app.openapi()["paths"]["/uuid-things/{thing_id}"]["get"]["parameters"][0]

    assert parameter["schema"] == {"type": "string", "format": "uuid", "title": "Thing Id"}
