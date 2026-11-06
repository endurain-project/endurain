"""The headers that name a related resource: ``Location`` on a create, ``Content-Location`` on a ``202``.

A ``201`` that carries the new resource still leaves the client to build its URL; ``Location`` (RFC 9110
§10.2.2) states it. It is set only where a GET-by-id route exists to point at.

A ``202`` answers only "queued". ``Content-Location`` (RFC 9110 §8.7) names the status resource the client
polls and ``Retry-After`` (RFC 9110 §10.2.3) says in seconds when to poll. The status read repeats
``Retry-After`` while the work is not finished.
"""

from typing import Any

from fastapi import Request, Response

import core.job_status as core_job_status

#: The OpenAPI declaration of a ``202`` that names its status resource, for a route's ``responses``.
ACCEPTED_RESPONSE: dict[int | str, dict[str, Any]] = {
    202: {
        "description": "Accepted. The work runs in the background and `Content-Location` names where to poll it.",
        "headers": {
            "Content-Location": {
                "description": "Path of the status resource to poll for the outcome.",
                "schema": {"type": "string"},
            },
            "Retry-After": {
                "description": "Seconds to wait before the first poll.",
                "schema": {"type": "integer"},
            },
        },
    }
}

#: The OpenAPI declaration of a status read that asks to be polled again while the work is running.
POLLED_STATUS_HEADERS: dict[str, Any] = {
    "Retry-After": {
        "description": "Seconds to wait before polling again. Sent only while the work is not finished.",
        "schema": {"type": "integer"},
    }
}


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


def set_retry_after(response: Response, seconds: int) -> None:
    """Send how long a client waits before it polls a status resource.

    Args:
        response: The response of the route.
        seconds: The wait.
    """
    response.headers["Retry-After"] = str(seconds)


def set_status_location(
    response: Response, request: Request, route_name: str, retry_after: int, **path_params: Any
) -> None:
    """Name the status resource of a ``202`` and say when to poll it.

    The value is a path, for the reason given on :func:`set_location`.

    Args:
        response: The response of the route that answers ``202``.
        request: The request, which resolves the route's path.
        route_name: The name of the route that reads the status.
        retry_after: Seconds before the first poll.
        **path_params: The route's path parameters.
    """
    response.headers["Content-Location"] = request.url_for(route_name, **path_params).path
    set_retry_after(response, retry_after)


def set_retry_after_while_running(response: Response, status: core_job_status.JobState, seconds: int) -> None:
    """Ask for another poll unless the status read reports the work is over.

    Args:
        response: The response of the status route.
        status: The status the read reports.
        seconds: The wait before the next poll.
    """
    if status not in core_job_status.TERMINAL_STATES:
        set_retry_after(response, seconds)
