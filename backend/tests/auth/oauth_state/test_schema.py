"""Tests for the OAuth-state create schema."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.schema as oauth_state_schema


def _values(**overrides):
    values = {
        "id": "a" * 32,
        "idp_id": uuid.uuid4(),
        "nonce": "n" * 32,
        "client_type": "web",
        "purpose": oauth_state_constants.OAuthStatePurpose.LOGIN,
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    values.update(overrides)
    return values


def test_idp_id_is_a_uuid_or_absent():
    idp_id = uuid.uuid4()

    assert oauth_state_schema.OAuthStateCreate(**_values(idp_id=idp_id)).idp_id == idp_id
    assert oauth_state_schema.OAuthStateCreate(**_values(idp_id=None)).idp_id is None


@pytest.mark.parametrize("bad_idp_id", [1, "not-a-uuid"])
def test_a_malformed_or_integer_idp_id_is_refused(bad_idp_id):
    with pytest.raises(ValidationError):
        oauth_state_schema.OAuthStateCreate(**_values(idp_id=bad_idp_id))
