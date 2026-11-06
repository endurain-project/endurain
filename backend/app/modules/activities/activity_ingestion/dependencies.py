"""Typed request parameters for the ingestion routers.

Each alias declares its constraint on the parameter's type, so FastAPI validates it, answers a bad
value with the standard validation problem document, and publishes the accepted shape in OpenAPI.
"""

from typing import Annotated

from fastapi import Header, Path

#: An ingestion job id taken from the path: the canonical form of the UUIDv4 the service issues.
JobId = Annotated[
    str,
    Path(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
]

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
