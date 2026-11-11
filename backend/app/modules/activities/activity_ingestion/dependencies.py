"""Typed request parameters for the ingestion routers.

Each alias declares its constraint on the parameter's type, so FastAPI validates it, answers a bad
value with the standard validation problem document, and publishes the accepted shape in OpenAPI.
"""

from typing import Annotated

from fastapi import Header

#: The optional ``Idempotency-Key`` header of an upload route, which makes a retry safe.
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        max_length=255,
        description=(
            "Optional client-generated key. Replaying a request with the same key returns "
            "the original job instead of importing the file again."
        ),
    ),
]
