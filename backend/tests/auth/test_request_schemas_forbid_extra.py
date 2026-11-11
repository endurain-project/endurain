"""Request-body schemas of the auth modules reject keys they do not declare."""

import pytest
from pydantic import ValidationError

import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.authentication.schema as auth_schema
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.mfa.schema as mfa_schema
import modules.auth.schema as step_up_schema
import modules.users.users.schema as users_schema

_PROVIDER = {"name": "Provider", "slug": "provider", "issuer_url": "https://idp.example.com"}

_CASES = [
    (
        api_keys_schema.UserApiKeyCreate,
        {"name": "CLI", "scopes": ["activities:upload"], "step_up": {"current_password": "secret"}},
    ),
    (auth_schema.TokenExchangeRequest, {"code_verifier": "a" * 43}),
    (users_schema.IdentityProviderLinkStart, {"step_up": {"current_password": "secret"}}),
    (mfa_schema.MFADisableRequest, {"step_up": {"current_password": "secret"}}),
    (mfa_schema.MFABackupCodesRequest, {"step_up": {"current_password": "secret"}}),
    (step_up_schema.StepUpRequest, {"step_up": {"current_password": "secret"}}),
    (idp_schema.IdentityProviderCreate, {**_PROVIDER, "client_secret": "secret"}),
    (idp_schema.IdentityProviderUpdate, _PROVIDER),
]


@pytest.mark.parametrize(("schema", "body"), _CASES, ids=[case[0].__name__ for case in _CASES])
def test_unknown_key_is_rejected(schema, body):
    schema(**body)

    with pytest.raises(ValidationError) as exc:
        schema(**body, unexpected="value")

    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_a_step_up_request_needs_the_step_up_object():
    with pytest.raises(ValidationError) as exc:
        step_up_schema.StepUpRequest()

    assert exc.value.errors()[0]["type"] == "missing"


def test_a_link_start_ends_other_sessions_unless_told_not_to():
    start = users_schema.IdentityProviderLinkStart(step_up={"current_password": "secret"})

    assert start.revoke_other_sessions is True
    assert (
        users_schema.IdentityProviderLinkStart(
            step_up={"current_password": "secret"}, revoke_other_sessions=False
        ).revoke_other_sessions
        is False
    )


def test_the_shared_step_up_request_has_no_revoke_flag():
    assert "revoke_other_sessions" not in step_up_schema.StepUpRequest.model_fields
