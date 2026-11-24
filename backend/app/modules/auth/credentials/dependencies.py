"""FastAPI providers for the credentials package."""

from typing import Annotated

from fastapi import Depends

import modules.auth.credentials.integration_service as credentials_integration

PasswordHasherDep = Annotated[
    credentials_integration.PasswordHasher, Depends(credentials_integration.get_password_hasher)
]
