"""Every route that takes a form or file body declares its own body cap.

``core.middleware_body_limit`` refuses a request body over the cap of the route it matches, and a route with no
cap falls back to the small JSON limit, so an upload route without one would reject every real upload.
"""

from fastapi import FastAPI, UploadFile

import core.middleware_body_limit as body_limit
import core.problem_details as core_problem_details
from api import router as api_router


def _uncapped(app: FastAPI) -> list[str]:
    """List the upload routes of an application that declare no body cap."""
    return [
        f"{sorted(route.methods)} {route.path}"
        for route in body_limit.upload_routes(app)
        if body_limit.route_limit(route) is None
    ]


def test_every_upload_route_of_the_api_declares_a_body_cap():
    app = core_problem_details.ProblemDetailsFastAPI()
    app.include_router(api_router)

    assert body_limit.upload_routes(app), "no upload route found; the check would pass for nothing"
    assert _uncapped(app) == []


def test_an_upload_route_without_a_cap_is_flagged():
    app = FastAPI()

    @app.post("/capped", openapi_extra=body_limit.upload_limit(1000))
    async def capped(file: UploadFile): ...

    @app.post("/uncapped")
    async def uncapped(file: UploadFile): ...

    assert _uncapped(app) == ["['POST'] /uncapped"]
