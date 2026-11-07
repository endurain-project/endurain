"""Contracts for access-token operations."""

from enum import Enum

import core.jwt_keys as core_jwt_keys


class TokenType(Enum):
    """The kind of JWT issued by the authentication module."""

    ACCESS = "access"
    REFRESH = "refresh"

    @property
    def header_type(self) -> str:
        """The JOSE ``typ`` header a token of this kind carries."""
        return core_jwt_keys.ACCESS_JWT_TYP if self is TokenType.ACCESS else core_jwt_keys.REFRESH_JWT_TYP
