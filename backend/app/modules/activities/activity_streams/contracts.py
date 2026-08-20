"""Package-owned internal data shapes for activity streams.

Separate from ``schema.py`` (the client-facing stream payloads) because these
never reach a client. They carry parser output into generic activity ingestion
and persistence projections into the stream service without leaking ORM rows.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedStream:
    """A parsed stream before its parent activity identifier is assigned."""

    stream_type: int
    stream_waypoints: list


@dataclass(frozen=True)
class HrStreamRecord:
    """Heart-rate stream columns owned by the streams package."""

    stream_id: int
    activity_id: int
    waypoints: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class HrStreamForScoring:
    """One heart-rate stream, with everything needed to compute its zones.

    Attributes:
        stream_id: The stream row's id, used to write the result back.
        activity_id: The activity the stream belongs to.
        owner_id: The activity owner, whose max heart rate scales the zones.
        waypoints: The recorded heart-rate samples.
        total_timer_time: The activity's moving time, which the breakdown is a
            proportion of. ``None`` when the activity never recorded one.
    """

    stream_id: int
    activity_id: int
    owner_id: int
    waypoints: list[dict] = field(default_factory=list)
    total_timer_time: float | None = None
