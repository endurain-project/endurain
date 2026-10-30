"""Request-body schemas of the auth modules reject keys they do not declare."""

import pytest
from pydantic import ValidationError

import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.authentication.schema as auth_schema
import modules.auth.identity_provider_link_tokens.schema as link_token_schema
import modules.auth.identity_providers.schema as idp_schema

_PROVIDER = {"name": "Provider", "slug": "provider"}

_CASES = [
    (api_keys_schema.UsersApiKeyCreate, {"name": "CLI", "scopes": ["activities:upload"]}),
    (auth_schema.TokenExchangeRequest, {"code_verifier": "a" * 43}),
    (link_token_schema.IdpLinkTokenRequest, {"current_password": "secret"}),
    (idp_schema.IdentityProviderCreate, {**_PROVIDER, "client_secret": "secret"}),
    (idp_schema.IdentityProviderUpdate, _PROVIDER),
]


@pytest.mark.parametrize(("schema", "body"), _CASES, ids=[case[0].__name__ for case in _CASES])
def test_unknown_key_is_rejected(schema, body):
    schema(**body)

    with pytest.raises(ValidationError) as exc:
        schema(**body, unexpected="value")

    assert exc.value.errors()[0]["type"] == "extra_forbidden"
