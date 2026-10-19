# Platform substrate (jasil)

`jasil` is the external first-party package that provides storage, events, durable jobs, geocoding and the surrounding plumbing.
Domain modules depend on its **capability ports**, never on its adapters.
The application wires it once in `core/platform_settings.py` (settings) and `main.py` / `worker.py` (container).

## Allowed surface

| Need | Import |
| --- | --- |
| Provider types (`StorageProvider`, `EventBusProvider`, geocoding...) | `jasil.providers` |
| Resolve the live platform outside a request | `jasil.runtime` (`get_active_platform()`) |
| Publish a domain event | `jasil.publisher` |
| Event envelope / subscribe | `jasil.events`, `jasil.subscribers` (`best_effort`) |
| Payload schemas + parsing | `jasil.event_versioning` (`VersionedPayload`, `parse_payload`) |
| Durable handler registration | `jasil.jobs.registry` (`JobHandlerRegistry`) |
| Reconciliation nets | `jasil.jobs.reconciliation` (`DurableSubscriberNet`) |

Forbidden (enforced by `tests/architecture/test_jasil_boundary.py`):
`jasil._core`, `jasil.backends`, `jasil.jobs.crud`, `jasil.event_log.crud`.
`core` and `jasil` never import `modules`.

## Storage

- Take it as an argument typed `jasil.providers.StorageProvider`; never resolve it inside a service, CRUD, pipeline or helper.
- Resolve it once at the entry point: routers use `Depends(core.dependencies.get_storage)`; subscribers, jobs and `integration_service` surface functions call `platform_runtime.get_active_platform()` and pass the provider down.
- The same applies to `geocoding`, `lock` and `state`.
- Tests then pass a `MagicMock()` or a real `LocalStorage`, and route tests use `app.dependency_overrides[get_storage]`; no runtime patching.
- `tests/architecture/test_module_boundaries.py::TestProviderResolution` fails on `get_active_platform` below an entry point.
- Each domain owns a storage *area* constant (`ACTIVITY_FILE_STORAGE_AREA = "activity_files"`); an area is a single namespace component, so put hierarchy in the key (`processed/42.fit`).
- Derive keys from ids; keep key builders next to the code that owns the area.
- Local disk and object storage behave identically; never assume a filesystem path.
- A new area needs an owner, a cleanup on parent deletion, a sweep for what an event missed and, for user data, removal on
  account deletion.
- User uploads still go through `core/file_uploads.py` first, then storage.
- Do not use `redis` directly; only the platform capability imports it.

## Publishing events

1. Declare the channel and payload in the owning module's `events.py`: `<domain>.<fact>`, past tense, payload extends `VersionedPayload` with `SCHEMA_VERSION`.
2. Publish from `event_publishers.py` with `platform_publisher.publish_committing(EVENT, payload, source=..., metadata={...}, db=db, commit=commit)`.
3. Call the publisher from `service`, which supplies the commit callable so the row and the outbox event commit atomically.
4. Never publish from `crud` or from `integration_service`.

## Subscribing

- Write the handler core as `<thing>_for_event(event)` that parses with `parse_payload(Payload, event)` and **raises** on failure (durable runner retries and dead-letters).
- Expose the bus subscriber as `best_effort(core)` so a derived-work failure never breaks the producing request.
- Open your own session (`core.database.SessionLocal()`); a subscriber has no request.
- Give each durable subscriber a stable id (`"activity_thumbnail.generate"`), independent of module path.
- Register from `subscriber_registry.py`: `register_bus_subscribers(events)`, `register_durable_handlers(registry)`, `DURABLE_SUBSCRIBER_NETS`.
- Then add one `RuntimeModule` entry in `app/module_registry.py`; never register in `main.py` or `worker.py` directly.
- Logging: DEBUG when skipping with the reason, ERROR when failing.

## Reconciliation nets

Delivery is at-least-once, never guaranteed, and some writes publish no event.
Each durable subscriber declares a `DurableSubscriberNet(subscriber_id, backfill_fn)`.
Use a scheduled backfill that re-derives what the create path missed, wired through `scheduled_jobs.recurring_jobs()`.
When no backfill is possible pass `None` plus `exempt_reason=...` explaining why.
`tests/architecture/test_reconciliation_nets.py` fails on a handler with neither.

## Scheduled and startup work

- Recurring work: `scheduled_jobs.recurring_jobs()` returning `core_scheduler.ScheduledJob(...)` tuples; one-shots via `core_scheduler.run_once(...)`.
- Startup backfills are `StartupTask`s on the module's `RuntimeModule`.
- The scheduler schedules what it is handed and imports no module.
- Everything must also run in `worker.py`; `module_registry` is what keeps API and worker from drifting.

## Config and profiles

- Runtime URIs come from settings: `STORAGE_URI` (default `local://`), `EVENTS_URI` -> `REDIS_URL` -> `memory://`, `JOBS_ENABLED`.
- The same code runs in-process (local) or distributed (Redis Streams, object storage); do not branch on the profile in domain code.
- Without `JOBS_ENABLED`, bus delivery is best-effort, which is why nets matter.
- Profiles differ in *delivery*, not in code: local subscribers run on a small background pool in the API process, distributed
  ones on a consumer or worker. Write every subscriber for the harder case: cheap, idempotent, own session, may run late, twice or never.
- Never hold a DB transaction across a storage, network or render call; end the read first (guide: Runtime behaviour).

## Tests

- `tests/conftest.py` installs a test platform through `jasil.testing.install_test_platform(tmp_path)` and resets it after; do not build providers by hand.
- Test handler cores directly with a constructed `Event`; test the `best_effort` wrapper separately.
- A new boundary rule that names a jasil module needs `test_the_private_surface_still_exists`-style pinning.
