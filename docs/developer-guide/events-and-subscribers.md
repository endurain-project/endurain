# Events and subscribers

This page is a how-to for reacting to something that happened, such as a new activity, without the code that caused it knowing about you. The rules behind it (layering, transactions, who may import what) are in [Module structure](module-structure.md). How events travel in a running deployment is in [Scaling and background jobs](../getting-started/scaling-and-background-jobs.md#how-events-are-delivered).

Use an event when you **react to a fact, derive state and tolerate delay**: thumbnails and geocoding react to `activity.created`. Do not use one for a plain query or for something the caller must wait for.

## The pieces

| Piece | File | Role |
| ----- | ---- | ---- |
| Event name and payload | `events.py` of the module that owns the fact | A constant such as `ACTIVITY_CREATED = "activity.created"` and a validated payload model. Convention: `<domain>.<fact>`, in the past tense. |
| Publisher | `event_publishers.py` | Stages the event. It does not commit. |
| Subscriber | `subscribers.py` | Reacts to the event. |
| Registration | `subscriber_registry.py` | Registers the bus subscribers and durable handlers and declares the reconciliation nets. |
| Wiring | `module_registry.py` | One `RuntimeModule` entry that the entry points read. |

## Publish an event

Add the channel and a payload to your module's `events.py`:

```python
ACTIVITY_CREATED = "activity.created"

class ActivityCreatedPayload(VersionedPayload):
    SCHEMA_VERSION: ClassVar[int] = 1
    activity_id: int
    user_id: int | None = None
```

Publish it from the service, in the same transaction as the change, through your `event_publishers.py`:

```python
activity_event_publishers.publish_activity_created(activity.id, activity.user_id, db=db, source="ingest:upload")
```

A publisher that takes no `commit` only stages the event, and the caller commits. One that takes `commit` is used by a service that ends the transaction itself, and runs that commit (see [Conventions that look like drift](module-structure.md#conventions-that-look-like-drift)). With durable jobs on, the event is written to the outbox in the caller's transaction, so it commits or rolls back with the rows. With them off, it is dispatched on the bus after the commit and dropped if the transaction rolls back.

Payloads are versioned. When a field is renamed, removed or changes meaning, raise `SCHEMA_VERSION` and register an upgrader. Adding an optional field needs no new version.

## Subscribe to an event

A subscriber is two functions. The first does the work and **raises** on failure, so the durable runner can retry and dead-letter it. The second wraps it for the best-effort bus and swallows errors, so the failure cannot break the request that caused the event.

```python
def generate_activity_thumbnail_for_event(event: Event) -> None:
    payload = parse_payload(activity_events.ActivityCreatedPayload, event)
    ...  # open your own session, do the work

on_activity_created_generate_thumbnail = best_effort(generate_activity_thumbnail_for_event)
```

Rules for the handler:

- **Open your own session.** It does not run inside the request.
- **Be idempotent.** Delivery is at least once, so it may run twice.
- **Assume it may not run at all.** A dropped event is repaired by the reconciliation net, not by the handler.
- **Parse the payload with `parse_payload`.** A payload from another build is upgraded or refused loudly.
- Never assume the work finished before the response was sent.

## Close what a dead-lettered job leaves open

A subscriber that drives state a user is waiting on (an import, a sync, an ingestion job) must leave
it in a terminal state when the runner gives up, or the user sees "processing" until a TTL expires.
Two things jasil provides make that exact:

- `event.is_last_attempt` says whether a failure now dead-letters the job. A handler that chooses
  between "stay queued for the retry" and "fail" reads it; it never compares `retry_count` with a
  setting. It is `False` outside a durable delivery, so the in-process path passes `will_retry=False`
  itself.
- `registry.register(..., on_dead_letter=callback)` runs `callback(event, error)` once the job has
  become `dead_letter`, whether its last attempt raised, its lease expired or its worker died. The
  handler's own `except` never sees the last two. The callback is at-least-once, so it must be
  idempotent: close the state only if it is still pending, and leave a finished or newer one alone.

```python
registry.register(
    garmin_events.GARMIN_SYNC_REQUESTED,
    SYNC_REQUESTED_SUBSCRIBER_ID,
    process_sync_requested_for_event,
    on_dead_letter=on_sync_requested_dead_letter,
)
```

A subscriber with nothing a user waits on (a thumbnail, a notification) needs neither: its
reconciliation net repairs what was lost.

## Register it

In `subscriber_registry.py`, register the bus subscriber and, for durable mode, a handler keyed by a stable subscriber id:

```python
THUMBNAIL_GENERATE_SUBSCRIBER_ID = "activity_thumbnail.generate"

events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_generate_thumbnail)
registry.register(activity_events.ACTIVITY_CREATED, THUMBNAIL_GENERATE_SUBSCRIBER_ID, generate_activity_thumbnail_for_event)
```

The id is independent of the module path, so job history and deduplication survive refactors. Pick it once and keep it.

The existing subscribers and their ids are listed in the [subscriber catalog](../getting-started/background-work-by-module.md#subscriber-catalog); add yours to it when you add one.

## Declare a reconciliation net

Every durable subscriber must say how lost work is repaired. Add a `DurableSubscriberNet` next to the registration:

```python
DURABLE_SUBSCRIBER_NETS = (
    DurableSubscriberNet(
        THUMBNAIL_GENERATE_SUBSCRIBER_ID,
        activity_thumbnail_scheduled_jobs.generate_missing_thumbnails,
    ),
)
```

The second argument is the scheduled backfill that finds and fixes what the event path missed. If a backfill makes no sense, for example for an admin-triggered command, pass `None` and give an `exempt_reason`. `tests/architecture/test_reconciliation_nets.py` fails if a durable subscriber has neither.

## Wire it up

Add one `RuntimeModule` to `MODULES` in `backend/app/module_registry.py`:

```python
RuntimeModule(
    name="activity_thumbnail",
    register_bus=activity_thumbnail_subscriber_registry.register_bus_subscribers,
    register_durable=activity_thumbnail_subscriber_registry.register_durable_handlers,
    nets=activity_thumbnail_subscriber_registry.DURABLE_SUBSCRIBER_NETS,
    recurring_jobs=activity_thumbnail_scheduled_jobs.recurring_jobs,
)
```

The entry points read this registry. They import your `subscriber_registry`, never your `subscribers`.

## Check your work

- Run `PYTHONPATH=app uv run lint-imports` and `uv run pytest tests/architecture -q` from `backend/`. They enforce the module boundaries, the registry and the reconciliation nets.
- Run with `JOBS_ENABLED=false` (best-effort bus) and `JOBS_ENABLED=true` (outbox and worker). A subscriber that works in only one mode is not done.
- Follow the event with `jasil_event_log` and `jasil_processing_jobs`; see [Troubleshooting](../getting-started/troubleshooting.md#follow-one-event).
