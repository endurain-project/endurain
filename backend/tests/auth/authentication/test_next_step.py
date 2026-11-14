"""Every sign-in answer says what comes next: the bodies carry a required ``next_step`` and the routes answer a union."""

import pytest
from fastapi import FastAPI

import modules.auth.account_security.public_router as password_change_router
import modules.auth.authentication.public_router as auth_router
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.sso_public_router as exchange_router
from tests.auth.authentication.conftest import BACKUP_CODE, CHALLENGE, MOBILE, PASSWORD, USERNAME, WEB

_BODIES = [
    ("MFARequiredRead", "mfa"),
    ("PasswordChangeRequiredRead", "password_change"),
    ("MobileSessionRead", "exchange"),
    ("TokenWebRead", "tokens"),
    ("TokenMobileRead", "tokens"),
]
_LOGIN = {"MFARequiredRead", "PasswordChangeRequiredRead", "MobileSessionRead", "TokenWebRead"}
_PASSWORD_CHANGE = {"MobileSessionRead", "TokenWebRead"}
# An identity-provider sign-in finishes at the MFA step with the tokens of either client type.
_MFA_VERIFY = (_LOGIN - {"MFARequiredRead"}) | {"TokenMobileRead"}
_EXCHANGE = {"MFARequiredRead", "TokenWebRead", "TokenMobileRead"}


@pytest.fixture(scope="module")
def openapi() -> dict:
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/auth")
    app.include_router(password_change_router.router, prefix="/auth")
    app.include_router(exchange_router.router, prefix="/auth")
    return app.openapi()


def _refs(node) -> set[str]:
    """Return the component names a response schema refers to, through any nested union."""
    if isinstance(node, dict):
        found = {node["$ref"].rsplit("/", 1)[-1]} if "$ref" in node else set()
        return found.union(*(_refs(value) for value in node.values()))
    if isinstance(node, list):
        return set().union(*(_refs(item) for item in node))
    return set()


def _response(openapi: dict, path: str) -> dict:
    return openapi["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]


class TestSchemas:
    @pytest.mark.parametrize(("name", "step"), _BODIES)
    def test_next_step_is_required_and_fixed(self, openapi, name, step):
        schema = openapi["components"]["schemas"][name]

        assert "next_step" in schema["required"]
        assert schema["properties"]["next_step"]["const"] == step
        assert "default" not in schema["properties"]["next_step"]

    def test_the_mfa_challenge_body_holds_the_challenge_and_the_methods(self, openapi):
        schema = openapi["components"]["schemas"]["MFARequiredRead"]

        assert set(schema["properties"]) == {"next_step", "mfa_challenge", "methods"}

    def test_the_password_change_body_holds_the_challenge_only(self, openapi):
        schema = openapi["components"]["schemas"]["PasswordChangeRequiredRead"]

        assert set(schema["properties"]) == {"next_step", "password_change_challenge"}

    def test_the_exchange_body_has_no_mfa_flag_or_message(self, openapi):
        schema = openapi["components"]["schemas"]["MobileSessionRead"]

        assert set(schema["properties"]) == {"next_step", "session_id", "device_id"}

    def test_a_body_without_next_step_is_refused(self):
        with pytest.raises(ValueError, match="next_step"):
            auth_schema.TokenWebRead.model_validate(
                {
                    "session_id": "s",
                    "access_token": "a",
                    "expires_in": 1,
                    "refresh_token_expires_in": 1,
                }
            )


class TestRoutes:
    @pytest.mark.parametrize(
        ("path", "bodies"),
        [("/auth/login", _LOGIN), ("/auth/password-change", _PASSWORD_CHANGE)],
    )
    def test_each_route_answers_the_bodies_it_can_end_in(self, openapi, path, bodies):
        schema = _response(openapi, path)

        assert _refs(schema) == bodies
        assert "oneOf" in schema

    @pytest.mark.parametrize(
        ("path", "bodies"),
        [("/auth/mfa/verify", _MFA_VERIFY), ("/auth/sessions/{session_id}/tokens", _EXCHANGE)],
    )
    def test_a_route_that_answers_both_token_bodies_answers_a_union_without_a_discriminator(
        self, openapi, path, bodies
    ):
        schema = _response(openapi, path)

        assert _refs(schema) == bodies
        assert "anyOf" in schema

    def test_refresh_still_answers_tokens_only(self, openapi):
        assert _refs(_response(openapi, "/auth/refresh")) == {"TokenWebRead", "TokenMobileRead"}

    def test_the_token_exchange_has_no_body_of_its_own(self, openapi):
        assert "TokenExchangeRead" not in openapi["components"]["schemas"]


class TestAnswers:
    def test_a_password_login_answers_tokens(self, plain_signin):
        response = plain_signin.client.post(
            "/auth/login", data={"username": USERNAME, "password": PASSWORD}, headers=WEB
        )

        body = response.json()
        assert response.status_code == 200
        assert body["next_step"] == "tokens"
        assert "mfa_required" not in body
        assert "message" not in body

    def test_a_mobile_pkce_login_answers_exchange(self, plain_signin):
        response = plain_signin.client.post(
            "/auth/login",
            data={
                "username": USERNAME,
                "password": PASSWORD,
                "code_challenge": CHALLENGE,
                "code_challenge_method": "S256",
            },
            headers=MOBILE,
        )

        body = response.json()
        assert body["next_step"] == "exchange"
        assert set(body) == {"next_step", "session_id", "device_id"}

    def test_an_mfa_account_answers_mfa_then_the_verified_login_answers_its_next_step(self, mfa_signin):
        first = mfa_signin.client.post("/auth/login", data={"username": USERNAME, "password": PASSWORD}, headers=WEB)

        assert first.json().keys() == {"next_step", "mfa_challenge", "methods"}
        assert first.json()["next_step"] == "mfa"

        second = mfa_signin.client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": first.json()["mfa_challenge"], "mfa_code": BACKUP_CODE},
            headers=WEB,
        )

        assert second.status_code == 200
        assert second.json()["next_step"] == "password_change"
