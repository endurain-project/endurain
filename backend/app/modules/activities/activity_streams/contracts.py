"""Inter-layer data shapes for activity streams.

Separate from ``schema.py`` (the client-facing stream payloads) because these
never reach a client: they are what the persistence layer hands its own service
so the ORM stays inside ``crud``.
"""

from dataclasses import dataclass, field


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
