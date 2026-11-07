"""``PositiveId`` keeps a path id inside the range of the integer columns it is looked up in."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions

_INT32_MAX = 2**31 - 1


@pytest.fixture
def client():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.get("/things/{thing_id}")
    def read_thing(thing_id: core_dependencies.PositiveId):
        return {"id": thing_id}

    return TestClient(app)


@pytest.mark.parametrize("thing_id", [1, _INT32_MAX])
def test_an_id_inside_the_column_range_is_accepted(client, thing_id):
    assert client.get(f"/things/{thing_id}").json() == {"id": thing_id}


@pytest.mark.parametrize("thing_id", [0, -1, _INT32_MAX + 1, 2**63])
def test_an_id_outside_the_column_range_is_a_validation_failure(client, thing_id):
    response = client.get(f"/things/{thing_id}")

    assert response.status_code == 422
    assert response.json()["type"] == "urn:endurain:error:validation-failed"
