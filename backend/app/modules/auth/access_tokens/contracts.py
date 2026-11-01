"""Contracts for access-token operations."""

from enum import Enum


class TokenType(Enum):
    """The kind of JWT issued by the authentication module."""

    ACCESS = "access"
    REFRESH = "refresh"
