"""The stream operations exposed only to data migrations."""

import modules.activities.activity_streams.crud as activity_streams_crud

get_activity_streams = activity_streams_crud.get_activity_streams
get_activity_stream_by_type = activity_streams_crud.get_activity_stream_by_type
