import pytest
from fastapi import HTTPException


class TestValidateIdpId:
    def test_valid(self):
        from modules.auth.identity_providers.dependencies import validate_idp_id

        validate_idp_id(1)
        validate_idp_id(100)

    def test_invalid(self):
        from modules.auth.identity_providers.dependencies import validate_idp_id

        with pytest.raises(HTTPException):
            validate_idp_id(0)

    def test_negative(self):
        from modules.auth.identity_providers.dependencies import validate_idp_id

        with pytest.raises(HTTPException):
            validate_idp_id(-1)
