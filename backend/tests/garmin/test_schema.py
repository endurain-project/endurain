"""Request-body schemas of the Garmin module reject keys they do not declare."""

import pytest
from pydantic import ValidationError

import modules.garmin.schema as garmin_schema

_CASES = [
    (garmin_schema.GarminLogin, {"username": "me", "password": "pw"}),
    (garmin_schema.MFARequest, {"mfa_code": "123456"}),
]


@pytest.mark.parametrize(("schema", "body"), _CASES, ids=[case[0].__name__ for case in _CASES])
def test_unknown_key_is_rejected(schema, body):
    schema(**body)

    with pytest.raises(ValidationError) as exc:
        schema(**body, unexpected="value")

    assert exc.value.errors()[0]["type"] == "extra_forbidden"
