"""The login form refuses NUL characters in any encoding of the form, including multipart, and over-long fields."""

import pytest

import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.credentials.integration_service as credentials_integration
from tests.auth.authentication.conftest import LOGIN, MOBILE, WEB, Account, login


def _refused_as_credentials(response) -> bool:
    """Whether the form was read and the sign-in refused for its credentials, not for its shape."""
    return response.status_code == 401


def _problem_field(response) -> str:
    body = response.json()
    assert body["type"] == "urn:endurain:error:validation-failed"
    return body["errors"][0]["field"]


def test_a_multipart_form_with_a_nul_is_a_validation_failure(client):
    response = client.post(LOGIN, files={"username": (None, "bob\x00"), "password": (None, "x")}, headers=WEB)

    assert response.status_code == 422
    assert _problem_field(response) == "body.username"


def test_a_urlencoded_form_with_a_nul_is_refused_before_the_form_is_read(client):
    response = client.post(LOGIN, data={"username": "bob", "password": "x\x00"}, headers=WEB)

    assert response.status_code == 422
    assert response.json()["type"] == "urn:endurain:error:validation-failed"


def test_the_optional_fields_are_checked_too(client):
    form = {"username": "bob", "password": "x", "code_challenge": "a\x00"}
    response = client.post(LOGIN, files={k: (None, v) for k, v in form.items()}, headers=MOBILE)

    assert response.status_code == 422
    assert _problem_field(response) == "body.code_challenge"


def test_the_login_body_declares_exactly_the_fields_the_server_reads(client):
    operation = client.app.openapi()["paths"][LOGIN]["post"]
    reference = operation["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]["$ref"]
    body = client.app.openapi()["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    assert set(body["properties"]) == {"username", "password", "code_challenge", "code_challenge_method"}
    assert set(body["required"]) == {"username", "password"}
    assert body["properties"]["password"]["format"] == "password"
    assert {p["name"] for p in operation["parameters"]} <= {"X-Client-Type", "X-Device-Id"}


@pytest.mark.parametrize("grant_type", ["password", "client_credentials"])
def test_a_grant_type_from_an_existing_client_is_ignored(client, grant_type):
    response = client.post(LOGIN, data={"username": "bob", "password": "x", "grant_type": grant_type}, headers=WEB)

    assert _refused_as_credentials(response)
    assert "grant_type" not in str(client.app.openapi()["paths"][LOGIN])


@pytest.mark.parametrize("field", ["scope", "client_id", "client_secret"])
def test_oauth2_fields_the_server_ignores_are_not_read(client, field):
    form = {"username": "bob", "password": "x", field: "a\x00"}

    response = client.post(LOGIN, files={k: (None, v) for k, v in form.items()}, headers=WEB)

    assert _refused_as_credentials(response)


@pytest.mark.parametrize("encode", ["data", "files"])
def test_a_clean_form_reaches_the_sign_in(client, account, encode):
    fields = {"username": account.username, "password": account.password}
    request = {"data": fields} if encode == "data" else {"files": {k: (None, v) for k, v in fields.items()}}

    assert client.post(LOGIN, headers=WEB, **request).status_code == 200


def test_the_username_is_trimmed_and_the_password_is_not(client, committed_sessions, account: Account):
    padded = " a padded passphrase 1 "
    with committed_sessions() as db:
        credentials_integration.set_local_password_hash(
            account.user.id,
            credentials_integration.get_password_hasher().hash_password(padded),
            db,
            change_required=False,
        )
        db.commit()

    assert login(client, account, username=f"  {account.username}  ", password=padded).status_code == 200
    assert login(client, account, password=padded.strip()).status_code == 401


@pytest.mark.parametrize("field", ["username", "password"])
def test_a_field_of_the_longest_allowed_length_reaches_the_sign_in(client, field):
    fields = {"username": "bob", "password": "x", field: "a" * authentication_dependencies.LOGIN_FIELD_MAX_LENGTH}

    assert _refused_as_credentials(client.post(LOGIN, data=fields, headers=WEB))


@pytest.mark.parametrize("field", ["username", "password"])
def test_a_field_over_the_limit_is_a_validation_failure_like_a_nul(client, field):
    fields = {"username": "bob", "password": "x", field: "a" * (authentication_dependencies.LOGIN_FIELD_MAX_LENGTH + 1)}

    response = client.post(LOGIN, data=fields, headers=WEB)

    assert response.status_code == 422
    assert _problem_field(response) == f"body.{field}"
