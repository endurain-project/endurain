"""Typed request parameters for the activity stream routers."""

from typing import Annotated

from fastapi import Path

import modules.activities.activity_streams.constants as activity_streams_constants

#: A stream type taken from the path. The exposed types run from heart rate up to the map track.
StreamType = Annotated[
    int, Path(ge=activity_streams_constants.STREAM_TYPE_HR, le=activity_streams_constants.STREAM_TYPE_MAP)
]
