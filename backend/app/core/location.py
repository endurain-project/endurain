"""The ``Location`` header a create answers with, naming where the new resource is read.

A ``201`` that carries the new resource still leaves the client to build its URL; ``Location`` (RFC 9110
§10.2.2) states it. It is set only where a GET-by-id route exists to point at.
"""

from typing import Any

from fastapi import Request, Response


def set_location(response: Response, request: Request, route_name: str, **path_params: Any) -> None:
    """Send the path of the route that reads the created resource as the response's ``Location``.

    The value is a path, not an absolute URL: behind a reverse proxy the scheme and host the app sees may not
    be the ones the client used, and RFC 9110 lets a client resolve a relative ``Location`` against the request.

    Args:
        response: The response the create route returns.
        request: The create request, which resolves the route's path.
        route_name: The name of the route that reads the resource by id.
        **path_params: The route's path parameters.
    """
    response.headers["Location"] = request.url_for(route_name, **path_params).path
