"""Version-aware payload parsing for durable and bus subscribers.

A subscriber never calls ``Model.model_validate(event.payload)`` directly; it
goes through :func:`parse_payload`, which compares the envelope's
``schema_version`` against the version the local code understands and does the
right thing for each direction of skew.

Why the direction matters
-------------------------
The writer and the reader of an event are frequently **not the same build**: an
event is staged in the outbox, relayed on a schedule, retried with exponential
backoff, and can sit dead-lettered indefinitely — and during a rolling deploy old
and new replicas serve traffic simultaneously.

* **Older event, newer consumer** (the common case — the outbox backlog after a
  deploy). This must actually work, so the payload model registers an explicit
  *upgrader* per version step. Silently defaulting a missing field is exactly the
  failure mode this module exists to prevent: every payload model sets
  ``extra="ignore"``, so a renamed or repurposed field would otherwise be dropped
  and read as its default, producing a wrong result with no error anywhere.
* **Newer event, older consumer** (a new replica publishes before the old workers
  drain). Nothing sensible can be done — the local code has never seen this
  shape. :class:`UnsupportedEventVersionError` is raised so the existing job
  machinery retries with backoff; the condition is self-healing, because by the
  time the attempts are spent the stale worker is normally gone. Failing loudly
  and retrying is strictly better than guessing.

No new machinery is needed for either: durable handlers already raise on failure
and the runner already retries and then dead-letters.
"""

from collections.abc import Callable
from typing import ClassVar

from pydantic import BaseModel

import core.logger as core_logger
from infra.events import Event

logger = core_logger.get_logger(__name__)


class UnsupportedEventVersionError(Exception):
    """Raised when an event's payload version is newer than this build understands.

    Deliberately an ordinary exception rather than a domain error: it is never
    seen by an HTTP caller, only by the durable-job runner (which retries, then
    dead-letters) or the best-effort bus wrapper (which logs and swallows).
    """


class VersionedPayload(BaseModel):
    """Base for every event payload model, carrying its own schema version.

    Subclasses set :attr:`SCHEMA_VERSION` and, once they have evolved past
    version 1, register an upgrader per version step in :attr:`UPGRADERS`.

    Both are ``ClassVar`` — without that annotation Pydantic would treat them as
    *model fields*, so they would be expected in every payload dict and would not
    be readable off the class at all.

    Attributes:
        SCHEMA_VERSION: The payload shape this build reads and writes.
        UPGRADERS: ``{from_version: fn(payload_dict) -> payload_dict}``, each
            entry converting a payload one version forward. Applied in sequence,
            so evolving 1 -> 3 only needs a 1->2 and a 2->3 entry.
    """

    SCHEMA_VERSION: ClassVar[int] = 1
    UPGRADERS: ClassVar[dict[int, Callable[[dict], dict]]] = {}


def parse_payload[T: VersionedPayload](model: type[T], event: Event) -> T:
    """Validate an event's payload, upgrading it from an older version if needed.

    Args:
        model: The payload model this subscriber consumes.
        event: The event envelope, carrying ``schema_version`` and ``payload``.

    Returns:
        The validated payload at the local build's schema version.

    Raises:
        UnsupportedEventVersionError: When the event was written by a newer build
            than this one.
        ValidationError: When the payload does not match its declared version.
    """
    target = model.SCHEMA_VERSION
    version = event.schema_version

    if version > target:
        logger.error(
            "Refusing an event written by a newer build",
            extra=core_logger.context(
                event_type=event.event_type,
                event_id=event.event_id,
                event_version=version,
                supported_version=target,
            ),
        )
        raise UnsupportedEventVersionError(
            f"{event.event_type} payload is version {version}; this build understands {target}"
        )

    payload = event.payload
    if version < target:
        logger.info(
            "Upgrading an event payload written by an older build",
            extra=core_logger.context(
                event_type=event.event_type,
                event_id=event.event_id,
                event_version=version,
                supported_version=target,
            ),
        )
        payload = _upgrade(model, payload, version, target, event)

    return model.model_validate(payload)


def _upgrade[T: VersionedPayload](
    model: type[T],
    payload: dict,
    version: int,
    target: int,
    event: Event,
) -> dict:
    """Apply the registered upgraders to walk a payload forward one step at a time.

    Args:
        model: The payload model whose upgraders to apply.
        payload: The payload as written.
        version: The version it was written at.
        target: The version to reach.
        event: The originating event, for error context.

    Returns:
        The upgraded payload dict.

    Raises:
        UnsupportedEventVersionError: When a step has no registered upgrader,
            which means an evolution shipped without its migration.
    """
    for step in range(version, target):
        upgrader = model.UPGRADERS.get(step)
        if upgrader is None:
            raise UnsupportedEventVersionError(
                f"{event.event_type} has no upgrader from payload version {step} to {step + 1}"
            )
        payload = upgrader(payload)
    return payload
