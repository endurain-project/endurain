# Module Structure

This guide defines the structure every backend module follows, and the rules that
make a module **replaceable**: you could lift `modules/activities` out of the tree,
publish it as a library, and the rest of the application would keep compiling
because it never depended on anything the module did not deliberately publish.

`modules/activities` is the reference implementation. Every other module — and
every new one — is converted to this shape.

## The two units

| Unit | What it is | Example |
| --- | --- | --- |
| **Module** | One bounded context. The unit of extraction. | `modules/activities` |
| **Sub-package** | One aggregate or subsystem inside a module. | `modules/activities/activity_laps` |

A module with a single aggregate stays flat (`modules/followers`). A module with
several — an activity is a root row, six child collections, three derived
artifacts and two ingestion paths — splits into sub-packages.

Sub-packages are **peers**, not a hierarchy. `activity_thumbnail` may not read
`activity_streams`' tables just because both live under `activities/`.

## File roles

Filenames are part of the contract: the enforcement rules match on them, so a
file named `crud.py` is treated as persistence wherever it appears.

| File | Layer | Responsibility |
| --- | --- | --- |
| `models.py` | persistence | SQLAlchemy ORM. The only place a table is declared. |
| `query.py` | persistence | Reusable SQL expression fragments. No session, no I/O. |
| `crud.py` | persistence | The **only** file that opens a `Session` against its own tables. Returns schemas/DTOs, never ORM rows. |
| `serializers.py` | persistence | ORM row → schema transformation. Receives rows *from* `crud`. |
| `service.py` | application | Decides access, orchestrates, publishes events, owns transaction boundaries. |
| `router.py` / `public_router.py` | transport | Validate, delegate to `service`, return. No domain rule. |
| `dependencies.py` | transport | FastAPI DI (path-param resolution, scope checks). |
| `schema.py` | contract | Pydantic request/response shapes. Serialized to clients. |
| `contracts.py` | contract | Inter-module DTOs and typed seams. Never serialized. |
| `constants.py` | contract | Domain constants and mapping tables. |
| `events.py` | contract | Event-type names and validated payload models. |
| `event_publishers.py` | application | Publishes this package's domain events. |
| `subscribers.py` | application | Handles events. Registered from `subscriber_registry`. |
| `integration_service.py` | **module surface** | The curated set of operations other modules may call. |
| `scheduled_jobs.py` | **module surface** | The module's recurring jobs, collected by the composition root. |

Anything else (`utils.py`, `signing.py`, `render.py`, `pipeline.py`, …) is
package-private by default.

## Visibility

Three classes. This is the whole rule.

### 1. Module surface — importable from anywhere

| Surface | Purpose |
| --- | --- |
| `integration_service.py` | Behaviour. Every cross-module call goes through it. |
| `contracts.py` | The data shapes that surface accepts and returns. |
| `schema.py` | Client-facing shapes, when a consumer genuinely needs the wire type. |
| `constants.py` | Stable domain constants. |
| `events.py` | Event names and payloads, so a consumer can subscribe. |
| `dependencies.py` | FastAPI DI, mounted at the HTTP boundary. |
| `router.py` / `public_router.py` | Mounted by `app/api.py` and nothing else. |
| `subscriber_registry.py` | Event wiring, called by `main.py` and `worker.py`. |
| `scheduled_jobs.py` | The module's recurring and one-shot background work, collected by `main.py`. |

### 2. Module-internal — importable by sibling sub-packages, not by other modules

`service.py`, and the named intra-module seams a module declares (for activities:
`activity/child_access.py`, `activity/ingestion_service.py`).

### 3. Package-private — importable only from inside its own sub-package

`crud.py`, `models.py`, `query.py`, `serializers.py`, `utils.py`, `subscribers.py`,
`event_publishers.py`, and every unlisted helper.

`__init__.py` holds a docstring and **nothing else**. A re-export facade would
hand out ORM models and CRUD functions under a package path, which is a silent
bypass of every rule above.

## Allowed-import matrix

Read as *row imports column*.

| From ↓ / To → | own `crud` | own `service` | sibling `crud` | sibling `service` | sibling `schema`/`contracts` | other module |
| --- | --- | --- | --- | --- | --- | --- |
| `router` | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ |
| `service` | ✓ | — | ✗ | ✓ | ✓ | `integration_service` only |
| `crud` | — | ✗ | ✗ | ✗ | ✓ | ✗ |
| `models` | — | ✗ | ✗ | ✗ | sibling `models` (FK only) | other-module `models` (FK only) |
| `subscribers` | ✗ | ✓ | ✗ | ✓ | ✓ | `integration_service` only |
| `integration_service` | ✓ | ✓ | ✓ | ✓ | ✓ | `integration_service` only |

Three entries deserve the reasoning:

- **`crud` never calls another module.** A `SELECT` that first has to ask another
  bounded context a question is a service-layer decision wearing a persistence
  layer's clothes.
- **`models` may cross boundaries.** SQLAlchemy relationships share one registry,
  so `Activity` ↔ `Gear` ↔ `Users` must name each other. These are `TYPE_CHECKING`
  imports describing a foreign key, not a behavioural reach.
- **`integration_service` may read its own module freely.** It *is* the module,
  presenting a narrow face outward.

## Layering inside a sub-package

```
router / public_router  →  service  →  crud  →  query / models
                              ↓
                     event_publishers → events
```

Downward only. `crud` never calls `service`; `service` never touches `models`.

## What a module may depend on

- **`core.*`** — cross-cutting primitives (logging, config, pagination, exceptions,
  timezone, signing, uploads). Always allowed.
- **`infra.*`** — the platform substrate, through `infra.providers` (ports) only.
  Never `infra.backends` (adapters).
- **Other modules** — through their `integration_service` only.
- **`fastapi`** — routers and dependencies only. Persistence raises
  `core.exceptions`; the app's error handler maps those to responses.

The dependency direction is fixed: `core` and `infra` must never import `modules`.
A module publishes its scheduled work (`scheduled_jobs.py`), its subscribers
(`subscriber_registry.py`) and its plug-ins; the platform *collects* them. It is
never the platform's job to know a module exists.

## Inverting a platform-to-domain reach

When the platform appears to need something from a module, the module registers
it rather than the platform importing it. Three worked examples live in the tree:

| Reach | Inversion |
| --- | --- |
| The scheduler needed each module's recurring jobs | Each module declares `scheduled_jobs.recurring_jobs()`; `main.py` collects and hands the list to `start_scheduler`. |
| Ingestion needed to pull from Strava and Garmin | Providers register a fetch callable on `activity_ingestion.provider_registry`; the refresh path names no provider. |
| Bulk import needed Strava-export semantics | `BulkImportSource` is a base class; `modules.strava.bulk_import_source.StravaBulkImportSource` subclasses it. |

The shape is always the same: the lower layer owns the *seam* (a registry, a base
class, a protocol), the higher layer owns the *implementation*, and a composition
root (`main.py`, `worker.py`) connects them. A registration performed in one
entrypoint must be performed in the other — a provider or subscriber registered
in the API but not the worker silently does nothing wherever its work is claimed.

## Enforcement

Two mechanisms, deliberately:

**`backend/.importlinter`** — cross-module rules, run in CI by
`.forgejo/workflows/test-backend.yml`:

```bash
cd backend && PYTHONPATH=app uv run lint-imports
```

Contracts are stated as **wildcards** (`modules.activities.*.crud`) so a new
sub-package inherits every rule the day it is created, instead of when someone
remembers to add it to a list.

**`backend/tests/architecture/test_module_boundaries.py`** — the one rule
import-linter cannot express. A `forbidden` contract rejects an import if *any*
source matches *any* forbidden module, so "a package may import its own `crud`
but not a sibling's" is not statable: the wildcard pair
`modules.activities.* → modules.activities.*.crud` also rejects
`activity_laps.service → activity_laps.crud`. The conformance test walks the AST,
compares each import against the importer's own package, and consults an explicit
allowlist of named seams.

That allowlist is the debt register. Every entry names a real cross-package reach
and why it is still there. Adding a new one is a deliberate, reviewed act; the
test fails on anything not listed.

## Adding a module

1. `modules/<name>/__init__.py` — docstring only.
2. One sub-package per aggregate; a single-aggregate module stays flat.
3. `integration_service.py` the first time another module needs something. Not
   before — an empty surface is worse than no surface.
4. `subscriber_registry.py` if the module has subscribers; register it in both
   `main.py` **and** `worker.py`.
5. `scheduled_jobs.py` if the module has recurring work; add it to the list
   `main.py` hands to `start_scheduler`.
6. Add the module to the source lists of the cross-module contracts in
   `backend/.importlinter`.
7. Add it to `_CONVERTED` in `backend/tests/architecture/test_module_boundaries.py`
   and in `backend/tests/test_logging_rule.py`.

## Known debt

Tracked here so it is visible rather than discovered. Each item is enumerated in
the conformance test's allowlist.

### Sibling persistence reaches

`activity_thumbnail`, `activity_geocoding` and `activity_media` read
`activity.crud` and `activity_streams.crud` directly. Each derived subsystem needs
a projection of the root row or its GPS stream; none of those reads is published
on a surface, so each subsystem reaches for the CRUD instead. The fix is a
read-projection seam per owning package.

`activity_summaries.crud` builds its own aggregates over `activity.models` and
`activity.query` — a second package issuing SQL against a table it does not own.

### Provider cycle

**Resolved.** `activity_ingestion` no longer imports `modules.strava` or
`modules.garmin`; the `activities-provider-agnostic` contract forbids the whole
module from doing so. Providers register on `provider_registry`, subclass
`BulkImportSource`, and resolve their own synced gear before handing a file to
ingestion.

### Platform → domain inversion

**Resolved for the scheduler.** `core/scheduler.py` schedules what it is handed
and imports no module; the `core-not-domain` contract enforces it.

One exception remains: `core/i18n` derives its supported-locale set from the
users module's `Language` enum. That is backwards — i18n owns which translation
bundles exist — and the enum should derive from `core.i18n`, not the reverse. It
is recorded as an `ignore_imports` entry rather than assumed.

### Migration → internals

`app/migrations/migration_*.py` import `activity.crud`, `activity_streams.crud`,
`activity_media.crud`, `activity_file_import.utils` and `activity_thumbnail.render`.
Data migrations are pinned to the schema of their era, so routing them through a
surface that evolves would break them; they are exempt by nature, and the exemption
is recorded rather than assumed.

### Consumers reaching past `integration_service`

`users_profile` (export/import) reaches `activity_file_storage.service` and
`activity_media.signing`; `strava.bulk_import_utils` reaches
`activity_media.service`; `strava.activity_utils` reaches
`activity_file_import.computation`. Profile export/import needs a wide slice of
the activities module, but "wide" is not "private".

The provider modules also reach `activity_ingestion.bulk_entry` and
`activity_ingestion.sources` to feed files in. That is the *correct* direction
(provider depends on activities) but not yet a published surface — the ingestion
entry point should be named on the module's surface rather than reached for by
path.
