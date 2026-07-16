"""
Activity streams module for stream data management.

This module provides activity stream data operations,
including retrieval, creation, and transformation of
heart rate, power, cadence, elevation, speed, pace,
and map streams.

Exports:
    - CRUD: get_activity_streams,
      get_activities_streams,
      get_public_activity_streams,
      get_activity_stream_by_type,
      get_public_activity_stream_by_type,
      create_activity_streams
    - Utils: transform_activity_streams,
      is_stream_hidden, filter_visible_streams
    - Schemas: ActivityStreams
    - Models: ActivityStreams (ORM model)
    - Constants: STREAM_TYPE_HR, STREAM_TYPE_POWER,
      STREAM_TYPE_CADENCE, STREAM_TYPE_ELEVATION,
      STREAM_TYPE_SPEED, STREAM_TYPE_PACE,
      STREAM_TYPE_MAP
"""

from .constants import (
    STREAM_TYPE_CADENCE,
    STREAM_TYPE_ELEVATION,
    STREAM_TYPE_HR,
    STREAM_TYPE_MAP,
    STREAM_TYPE_PACE,
    STREAM_TYPE_POWER,
    STREAM_TYPE_SPEED,
)
from .crud import (
    create_activity_streams,
    get_activities_streams,
    get_activity_stream_by_type,
    get_activity_streams,
    get_public_activity_stream_by_type,
    get_public_activity_streams,
)
from .models import (
    ActivityStreams as ActivityStreamsModel,
)
from .schema import (
    ActivityStreamsBase,
    ActivityStreamsCreate,
    ActivityStreamsRead,
)
from .utils import (
    filter_visible_streams,
    is_stream_hidden,
    transform_activity_streams,
)

__all__ = [
    "STREAM_TYPE_CADENCE",
    "STREAM_TYPE_ELEVATION",
    "STREAM_TYPE_HR",
    "STREAM_TYPE_MAP",
    "STREAM_TYPE_PACE",
    "STREAM_TYPE_POWER",
    "STREAM_TYPE_SPEED",
    "ActivityStreamsBase",
    "ActivityStreamsCreate",
    "ActivityStreamsModel",
    "ActivityStreamsRead",
    "create_activity_streams",
    "filter_visible_streams",
    "get_activities_streams",
    "get_activity_stream_by_type",
    "get_activity_streams",
    "get_public_activity_stream_by_type",
    "get_public_activity_streams",
    "is_stream_hidden",
    "transform_activity_streams",
]
