"""ORM↔schema transformation for activity streams.

The counterpart of :mod:`modules.activities.activity.serializers`, and named to
match: ``crud`` calls the transformation at its edges so ORM rows never leave the
persistence layer. Visibility masking is an access decision and lives in
:mod:`modules.activities.activity_streams.service`.
"""

import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.models as activity_streams_models
import modules.activities.activity_streams.schema as activity_streams_schema


def to_read_schema(
    activity_stream: activity_streams_models.ActivityStreams,
) -> activity_streams_schema.ActivityStreamsRead:
    """Transform a stream to a Pydantic schema.

    Args:
        activity_stream: The stream ORM instance.

    Returns:
        The activity stream as a schema.
    """
    return activity_streams_schema.ActivityStreamsRead.model_validate(activity_stream)


def to_read_schemas(
    activity_streams: list[activity_streams_models.ActivityStreams],
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Transform a list of streams to a list of Pydantic schemas.

    Args:
        activity_streams: The stream ORM instances.

    Returns:
        The activity streams as schemas.
    """
    return [to_read_schema(stream) for stream in activity_streams]


def to_parsed_samples(
    samples: activity_streams_models.ActivitySamples,
) -> activity_streams_contracts.ParsedSamples:
    """Transform a samples row to its contract.

    Args:
        samples: The samples ORM instance.

    Returns:
        The samples with their arrays copied out of the row.
    """
    return activity_streams_contracts.ParsedSamples(
        offsets_ms=list(samples.offsets_ms),
        **{name: getattr(samples, name) for name in activity_streams_constants.SAMPLE_CHANNELS},
    )
