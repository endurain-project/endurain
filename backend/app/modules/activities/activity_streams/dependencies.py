"""Typed request parameters for the activity stream routers."""

from typing import Annotated

from fastapi import Path

import modules.activities.activity_streams.constants as activity_streams_constants

#: A stream type taken from the path.
StreamType = Annotated[activity_streams_constants.ActivityStreamType, Path()]
