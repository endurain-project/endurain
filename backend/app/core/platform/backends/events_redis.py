"""Redis Streams ``EventBusProvider`` backend.

Only imported by the composition root when ``EVENTS_URI`` (or the shared
``REDIS_URL``) selects Redis, so ``local`` deployments never load it. Publishing
is an ``XADD`` onto one stream; a background consumer thread reads through a
consumer group (``XREADGROUP``) and dispatches each event to the subscribers
registered for its ``event_type``, acking (``XACK``) after the handlers run.

Endurain ships one image, so every replica registers the same subscribers. A
single consumer group therefore gives "each derived computation runs once per
event across the cluster" (competing consumers), while in-process fan-out to all
handlers of an ``event_type`` still happens on whichever replica claims the entry.

Delivery is at-least-once: an entry is acked only after its handlers succeed, so
a failed handler (or a malformed envelope) leaves the entry pending rather than
dropping it. This bus is the *best-effort* delivery path and has no in-bus retry
or reclaim of its own: an entry orphaned by a crashed consumer (which would need
``XAUTOCLAIM``/``XPENDING`` to recover) stays pending. For at-least-once delivery
with per-subscriber retry, backoff, dead-letter, and replay, enable durable jobs
(``JOBS_ENABLED``, foundations plan F8): publishing then routes through the
transactional outbox and ``processing_jobs`` instead of this bus. For the
thumbnail use case the hourly scheduler backfill is the reconciliation net.
"""

import json
import threading
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import core.logger as core_logger
import core.platform.node as platform_node
import core.platform.redis as platform_redis
from core.platform.events import Event

if TYPE_CHECKING:
    from core.platform.providers import EventRecorder

_DEFAULT_STREAM = "endurain:events"
_DEFAULT_GROUP = "endurain"
_STREAM_MAXLEN = 10_000  # approximate cap so acked entries don't grow unbounded
_READ_BATCH = 10
_BLOCK_MS = 1_000  # XREADGROUP block window; bounds how quickly stop() is observed
_STOP_JOIN_TIMEOUT = 5.0


def serialize_event(event: Event) -> dict[str, str]:
    """Flatten an :class:`Event` into Redis stream fields (all strings)."""
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "source": event.source,
        "timestamp": event.timestamp,
        "payload": json.dumps(event.payload),
        "metadata": json.dumps(event.metadata),
        "retry_count": str(event.retry_count),
    }


def deserialize_event(fields: Mapping[str, str]) -> Event:
    """Rebuild an :class:`Event` from Redis stream fields (the inverse of :func:`serialize_event`)."""
    return Event(
        event_id=fields["event_id"],
        event_type=fields["event_type"],
        source=fields["source"],
        timestamp=fields["timestamp"],
        payload=json.loads(fields["payload"]),
        metadata=json.loads(fields["metadata"]),
        retry_count=int(fields["retry_count"]),
    )


class RedisStreamEventBus:
    """``EventBusProvider`` backed by one Redis stream and a consumer group.

    The Redis client is typed ``Any`` to stay clear of redis-py's sync/async
    ``ResponseT`` typing; :meth:`from_uri` builds a ``decode_responses=True``
    client so stream fields arrive as ``str``.
    """

    def __init__(
        self,
        client: Any,
        *,
        stream: str = _DEFAULT_STREAM,
        group: str = _DEFAULT_GROUP,
        consumer: str | None = None,
        recorder: "EventRecorder | None" = None,
    ) -> None:
        self._client = client
        self._stream = stream
        self._group = group
        self._consumer = consumer or platform_node.process_identity()
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._recorder = recorder

    @classmethod
    def from_uri(
        cls,
        uri: str,
        *,
        stream: str = _DEFAULT_STREAM,
        group: str = _DEFAULT_GROUP,
        recorder: "EventRecorder | None" = None,
    ) -> "RedisStreamEventBus":
        """Build from a ``redis://…`` URI, verifying connectivity eagerly."""
        client = platform_redis.get_shared_client(uri, purpose="event bus")
        return cls(client, stream=stream, group=group, recorder=recorder)

    def publish(self, event: Event) -> None:
        # Record 'published' from the producer process before the entry is queued;
        # the consumer records processing/completed/failed when it claims the entry.
        if self._recorder is not None:
            self._recorder.record_published(event)
        self._client.xadd(self._stream, serialize_event(event), maxlen=_STREAM_MAXLEN, approximate=True)

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._handlers[event_type].append(handler)

    def start(self) -> None:
        """Create the consumer group (idempotent) and start the consumer thread."""
        if self._thread is not None:
            return
        self._ensure_group()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="event-bus-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the consumer thread and wait briefly for it to finish."""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=_STOP_JOIN_TIMEOUT)

    def _ensure_group(self) -> None:
        try:
            self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except platform_redis.ResponseError as error:
            if "BUSYGROUP" not in str(error):  # any error other than "group already exists" is real
                raise

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except platform_redis.RedisError as error:
                core_logger.print_to_log("Event bus consumer poll failed", "error", exc=error)
                self._stop.wait(timeout=1.0)

    def _poll_once(self) -> None:
        response = self._client.xreadgroup(
            self._group, self._consumer, {self._stream: ">"}, count=_READ_BATCH, block=_BLOCK_MS
        )
        for _stream, entries in response or []:
            for entry_id, fields in entries:
                self._dispatch(entry_id, fields)

    def _dispatch(self, entry_id: str, fields: Mapping[str, str]) -> None:
        recorder = self._recorder
        try:
            event = deserialize_event(fields)
            handlers = self._handlers.get(event.event_type, [])
            if recorder is None:
                for handler in handlers:
                    handler(event)
            else:
                handler_name = ",".join(handler.__name__ for handler in handlers) or None
                with recorder.track(event, worker_id=self._consumer, handler_name=handler_name):
                    for handler in handlers:
                        handler(event)
        except Exception as error:  # a poisoned entry or handler must not kill the consumer thread
            core_logger.print_to_log(
                f"Event handler failed for stream entry {entry_id}; leaving it pending", "error", exc=error
            )
            return
        # Ack only after success so a failure stays pending (at-least-once) for
        # reprocessing; durable jobs (F8) provide the retry/dead-letter path.
        self._client.xack(self._stream, self._group, entry_id)
