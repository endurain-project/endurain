"""Every sign-in answer says what comes next: the bodies carry a required ``next_step`` and the routes answer a
union."""

import pytest

import modules.auth.authentication.schema as auth_schema

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


@pytest.fixture
def openapi(client) -> dict:
    return client.app.openapi()


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
        [("/api/v1/auth/login", _LOGIN), ("/api/v1/auth/password-change", _PASSWORD_CHANGE)],
    )
    def test_each_route_answers_the_bodies_it_can_end_in(self, openapi, path, bodies):
        schema = _response(openapi, path)

        assert _refs(schema) == bodies
        assert "oneOf" in schema

    @pytest.mark.parametrize(
        ("path", "bodies"),
        [("/api/v1/auth/mfa/verify", _MFA_VERIFY), ("/api/v1/auth/sessions/{session_id}/tokens", _EXCHANGE)],
    )
    def test_a_route_that_answers_both_token_bodies_answers_a_union_without_a_discriminator(
        self, openapi, path, bodies
    ):
        schema = _response(openapi, path)

        assert _refs(schema) == bodies
        assert "anyOf" in schema

    def test_refresh_still_answers_tokens_only(self, openapi):
        assert _refs(_response(openapi, "/api/v1/auth/refresh")) == {"TokenWebRead", "TokenMobileRead"}

    def test_the_token_exchange_has_no_body_of_its_own(self, openapi):
        assert "TokenExchangeRead" not in openapi["components"]["schemas"]
