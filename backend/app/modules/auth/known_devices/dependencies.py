"""The device id a client keeps, read at the HTTP boundary: a web browser in a cookie, the mobile app in a header."""

import math
import re
from typing import Annotated

from fastapi import Cookie, Depends, Header, Response

import core.config as core_config
import modules.auth.computation as auth_computation
import modules.auth.known_devices.constants as known_devices_constants

#: The cookie that names the browser a user signs in from. It is sent only to the API, and Strict because every
#: sign-in that reads it is a same-site request from the web app.
DEVICE_COOKIE_NAME = "endurain_device"
#: The header the mobile app, which keeps no cookies, sends its device id in.
DEVICE_HEADER_NAME = "X-Device-Id"
#: The API root: the narrowest path that reaches both ``/auth`` (password and MFA sign-in) and ``/public/idp``
#: (the SSO token exchange).
DEVICE_COOKIE_PATH = core_config.ROOT_PATH
_DEVICE_COOKIE_MAX_AGE_SECONDS = known_devices_constants.DEVICE_RETENTION_DAYS * 24 * 60 * 60
_DEVICE_ID_PATTERN = re.compile(rf"[A-Za-z0-9_-]{{{math.ceil(known_devices_constants.DEVICE_ID_BYTES * 4 / 3)}}}")


def get_device_id(
    device_cookie: Annotated[str | None, Cookie(alias=DEVICE_COOKIE_NAME, include_in_schema=False)] = None,
    device_header: Annotated[str | None, Header(alias=DEVICE_HEADER_NAME, include_in_schema=False)] = None,
) -> str | None:
    """Return the device id the client sent, or None when it sent none or a malformed one.

    The mobile app's header wins over a cookie; a browser sends only the cookie.

    Args:
        device_cookie: The raw cookie value.
        device_header: The raw ``X-Device-Id`` header value.

    Returns:
        The device id, or None.
    """
    device_id = device_header if device_header is not None else device_cookie
    if device_id is None or _DEVICE_ID_PATTERN.fullmatch(device_id) is None:
        return None
    return device_id


DeviceId = Annotated[str | None, Depends(get_device_id)]


def set_device_cookie(response: Response, device_id: str) -> None:
    """Keep the device id in the browser for the retention period, counted from this sign-in.

    Args:
        response: The response that completes the sign-in.
        device_id: The device id the sign-in recorded.
    """
    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=device_id,
        max_age=_DEVICE_COOKIE_MAX_AGE_SECONDS,
        path=DEVICE_COOKIE_PATH,
        httponly=True,
        secure=auth_computation.secure_cookie(core_config.settings.ENVIRONMENT),
        samesite="strict",
    )
