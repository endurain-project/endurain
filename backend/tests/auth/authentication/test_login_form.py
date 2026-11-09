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
    response = client.post("/login", data={"username": "bob", "password": "x", "grant_type": "password\x00"})

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "body.grant_type"


def test_the_login_body_declares_exactly_the_fields_the_server_reads(client):
    schemas = client.app.openapi()["components"]["schemas"]
    (body,) = [schema for name, schema in schemas.items() if name.startswith("Body_")]

    assert set(body["properties"]) == {"username", "password", "grant_type", "code_challenge", "code_challenge_method"}
    assert set(body["required"]) == {"username", "password"}
    assert body["properties"]["password"]["format"] == "password"


def test_grant_type_password_is_accepted_and_any_other_grant_is_refused(client):
    fields = {"username": "bob", "password": "x"}

    assert client.post("/login", data={**fields, "grant_type": "password"}).status_code == 200
    assert client.post("/login", data=fields).status_code == 200
    assert client.post("/login", data={**fields, "grant_type": "client_credentials"}).status_code == 422


@pytest.mark.parametrize("field", ["scope", "client_id", "client_secret"])
def test_oauth2_fields_the_server_ignores_are_not_read(client, field):
    assert client.post("/login", data={"username": "bob", "password": "x", field: "a\x00"}).status_code == 200


@pytest.mark.parametrize("encode", ["data", "files"])
def test_a_clean_form_reaches_the_route(client, encode):
    fields = {"username": "bob", "password": "x"}
    request = {"data": fields} if encode == "data" else {"files": {k: (None, v) for k, v in fields.items()}}

    assert client.post("/login", **request).json() == {"username": "bob"}


def test_the_username_is_trimmed_and_the_password_is_not(client):
    response = client.post("/login", data={"username": "  bob  ", "password": " x "})

    assert response.json() == {"username": "bob"}
    assert client.post("/login", data={"username": "bob", "password": " x "}).status_code == 200


@pytest.mark.parametrize("field", ["username", "password"])
def test_a_field_of_the_longest_allowed_length_reaches_the_route(client, field):
    fields = {"username": "bob", "password": "x", field: "a" * authentication_dependencies.LOGIN_FIELD_MAX_LENGTH}

    assert client.post("/login", data=fields).status_code == 200


@pytest.mark.parametrize("field", ["username", "password"])
def test_a_field_over_the_limit_is_a_validation_failure_like_a_nul(client, field):
    fields = {"username": "bob", "password": "x", field: "a" * (authentication_dependencies.LOGIN_FIELD_MAX_LENGTH + 1)}

    response = client.post("/login", data=fields)

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "urn:endurain:error:validation-failed"
    assert body["errors"][0]["field"] == f"body.{field}"


def test_the_login_limit_covers_the_longest_password_a_user_can_set():
    assert authentication_dependencies.LOGIN_FIELD_MAX_LENGTH == 256
