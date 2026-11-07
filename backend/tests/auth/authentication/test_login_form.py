"""The login form refuses NUL characters in any encoding of the form, including multipart."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import modules.auth.authentication.dependencies as authentication_dependencies


@pytest.fixture
def client():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.post("/login")
    def login(form_data: authentication_dependencies.LoginForm):
        return {"username": form_data.username}

    return TestClient(app, headers={"X-Client-Type": "web"})


def test_a_multipart_form_with_a_nul_is_a_validation_failure(client):
    response = client.post("/login", files={"username": (None, "bob\x00"), "password": (None, "x")})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:endurain:error:validation-failed"
    assert body["errors"][0]["field"] == "body.username"


def test_a_urlencoded_form_with_a_nul_is_a_validation_failure(client):
    response = client.post("/login", data={"username": "bob", "password": "x\x00"})

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "body.password"


def test_the_optional_fields_are_checked_too(client):
    response = client.post("/login", data={"username": "bob", "password": "x", "scope": "a\x00"})

    assert response.status_code == 422


@pytest.mark.parametrize("encode", ["data", "files"])
def test_a_clean_form_reaches_the_route(client, encode):
    fields = {"username": "bob", "password": "x"}
    request = {"data": fields} if encode == "data" else {"files": {k: (None, v) for k, v in fields.items()}}

    assert client.post("/login", **request).json() == {"username": "bob"}


def test_the_username_is_trimmed_and_the_password_is_not(client):
    response = client.post("/login", data={"username": "  bob  ", "password": " x "})

    assert response.json() == {"username": "bob"}
    assert client.post("/login", data={"username": "bob", "password": " x "}).status_code == 200
