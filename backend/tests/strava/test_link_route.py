"""The Strava routes sit behind the access-token check."""

import modules.strava.router as strava_router


def test_the_link_route_requires_authentication():
    deps = {d.call for d in strava_router.router.routes[0].dependant.dependencies}
    assert strava_router.auth_dependencies.validate_access_token in deps
