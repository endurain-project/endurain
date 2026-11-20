"""FastAPI providers for the access-token package."""

from typing import Annotated

from fastapi import Depends

import modules.auth.access_tokens.integration_service as access_tokens_integration

TokenManagerDep = Annotated[
    access_tokens_integration.TokenManager, Depends(access_tokens_integration.get_token_manager)
]
