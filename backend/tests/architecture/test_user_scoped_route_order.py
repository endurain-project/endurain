"""Routes under ``/users/{user_id}`` never shadow the literal ``/users/id`` and ``/users/username`` paths.

Starlette resolves routes in registration order, so a ``/{user_id}/<resource>`` route mounted before the users
routers would answer ``/users/id/<name>`` with ``user_id="id"``.
"""

import pytest
from fastapi import FastAPI

import api as app_api
import core.config as core_config

_USERS = core_config.ROOT_PATH + "/users"
_LITERALS = (f"{_USERS}/id/{{user_id}}", f"{_USERS}/username/{{username}}")


def _registered_paths() -> list[str]:
    """Return every API path in the order the app registers them."""
    app = FastAPI()
    app.include_router(app_api.router)
    return list(app.openapi()["paths"])


@pytest.mark.parametrize("literal", _LITERALS)
def test_the_literal_users_paths_are_registered_before_every_user_resource(literal):
    paths = _registered_paths()
    # The profile photo is mounted first on purpose (see api.py) and is not one of these resources.
    resources = [path for path in paths if path.startswith(f"{_USERS}/{{user_id}}/") and not path.endswith("/photo")]

    assert resources, "no /users/{user_id}/<resource> route is registered"
    assert paths.index(literal) < min(paths.index(path) for path in resources)
