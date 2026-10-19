"""Typed request parameters for the ingestion routers.

Each alias declares its constraint on the parameter's type, so FastAPI validates it, answers a bad
value with the standard validation problem document, and publishes the accepted shape in OpenAPI.
"""

from typing import Annotated

from fastapi import Path

#: An ingestion job id taken from the path: the canonical form of the UUIDv4 the service issues.
JobId = Annotated[
    str,
    Path(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"),
]
