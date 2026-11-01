"""Typed request parameters for the activity stream routers."""

from typing import Annotated

from fastapi import Path

import modules.activities.activity_streams.constants as activity_streams_constants

#: A stream type taken from the path. The stored types run from heart rate up to temperature, so a type
#: the list route returns can also be read on its own.
StreamType = Annotated[
    int, Path(ge=activity_streams_constants.STREAM_TYPE_HR, le=activity_streams_constants.STREAM_TYPE_TEMPERATURE)
]
