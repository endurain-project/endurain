"""Typed request parameters for the activity stream routers."""

from typing import Annotated

from fastapi import Query

#: The most samples a client wants back; the activity's samples are averaged into that many equal-time buckets.
MaxPoints = Annotated[
    int | None,
    Query(
        ge=2,
        le=10000,
        description=(
            "The most samples to return. A longer activity is averaged over this many equal-time buckets; "
            "omitted, every sample is returned"
        ),
    ),
]
