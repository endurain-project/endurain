"""An identity-provider slug shares path segments with the fixed words of the public identity-provider routes.

A route table walk keeps ``RESERVED_SLUGS`` in step: a new static segment under ``/public/idp`` fails here until
it is reserved.
"""

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts

import core.config as core_config
import modules.auth.identity_providers.constants as idp_constants
from api import router as api_router

_PREFIX = core_config.ROOT_PATH + "/public/idp"


def _static_segments_under_the_prefix() -> set[str]:
    app = FastAPI()
    app.include_router(api_router)
    segments: set[str] = set()
    for route in iter_route_contexts(app.routes):
        path = route.path or ""
        if not path.startswith(_PREFIX + "/"):
            continue
        segments.update(
            segment for segment in path.removeprefix(_PREFIX + "/").split("/") if not segment.startswith("{")
        )
    return segments


def test_every_static_segment_under_the_public_idp_prefix_is_a_reserved_slug():
    # Arrange & Act
    segments = _static_segments_under_the_prefix()

    # Assert
    assert segments, "no public identity-provider route found: the prefix changed"
    missing = segments - idp_constants.RESERVED_SLUGS
    assert not missing, f"Add {sorted(missing)} to RESERVED_SLUGS in identity_providers/constants.py"
