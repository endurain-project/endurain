"""Gear request-parameter types."""

from typing import Annotated

from fastapi import Path

GearNickname = Annotated[str, Path(min_length=1, max_length=250)]
