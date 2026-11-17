"""The ``If-Match`` header a write must carry."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions


def test_a_missing_header_is_refused_as_precondition_required():
    with pytest.raises(core_exceptions.PreconditionRequiredError) as refused:
        core_dependencies.require_if_match_header(None)

    assert refused.value.status_code == 428


def test_the_header_is_handed_through():
    assert core_dependencies.require_if_match_header('"7"') == '"7"'


def test_a_wildcard_is_refused_so_a_client_cannot_skip_the_stale_write_check():
    with pytest.raises(core_exceptions.InvalidInputError):
        core_dependencies.require_if_match_header("*")

    with pytest.raises(core_exceptions.InvalidInputError):
        core_dependencies.require_if_match_header('"3", *')


def test_a_route_declaring_it_answers_428_without_the_header():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.patch("/thing")
    def edit(if_match: core_dependencies.IfMatch) -> dict[str, str]:
        return {"if_match": if_match}

    client = TestClient(app)

    assert client.patch("/thing").status_code == 428
    assert client.patch("/thing", headers={"If-Match": '"3"'}).json() == {"if_match": '"3"'}
