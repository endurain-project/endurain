"""Request-parameter types for the followers routes."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.exceptions import RequestValidationError

import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies


def get_other_user_id(user_id: core_dependencies.UuidId, token_user_id: auth_dependencies.CurrentUserId) -> uuid.UUID:
    """Return the ``{user_id}`` path parameter, which must name someone other than the caller.

    Args:
        user_id: The user the route acts on.
        token_user_id: The authenticated caller.

    Returns:
        The user id.

    Raises:
        RequestValidationError: When the id is the caller's own (422).
    """
    if user_id == token_user_id:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("path", "user_id"),
                    "msg": "user_id must not be your own",
                    "input": user_id,
                }
            ]
        )
    return user_id


OtherUserId = Annotated[uuid.UUID, Depends(get_other_user_id)]
