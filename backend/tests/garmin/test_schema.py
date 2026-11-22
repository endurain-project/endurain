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


class TestMFARequestNormalisation:
    """A pasted or autofilled code reaches Garmin without separators."""

    @pytest.mark.parametrize("submitted", ["123456", " 123 456 ", "123-456", "123\t456\n"])
    def test_whitespace_and_dashes_are_stripped(self, submitted):
        assert garmin_schema.MFARequest(mfa_code=submitted).mfa_code == "123456"

    @pytest.mark.parametrize("submitted", ["", "  ", "---", "12$456"])
    def test_a_code_that_is_not_alphanumeric_is_rejected(self, submitted):
        with pytest.raises(ValidationError):
            garmin_schema.MFARequest(mfa_code=submitted)
