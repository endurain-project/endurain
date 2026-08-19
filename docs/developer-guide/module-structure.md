# Module Structure

This guide defines the structure every backend module follows, and the rules that
make a module **replaceable**: you could lift `modules/activities` out of the tree,
publish it as a library, and the rest of the application would keep compiling
because it never depended on anything the module did not deliberately publish.

`modules/activities` is the reference implementation for a module that splits
into sub-packages; `modules/followers` is the reference for one that stays flat.
Every other module — and every new one — is converted to this shape.

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

The corollary is that a misnamed file is *silently exempt*. `activity_ingestion`
held its persistence in `ingestion_jobs_crud.py`, which no `modules.activities.*.crud`
wildcard matched — so the one CRUD module in the tree that routers were free to
import was the one nobody had noticed was named wrong. Renaming it to `crud.py`
brought it under four existing contracts without writing a new one.

| File | Layer | Responsibility |
| --- | --- | --- |
| `models.py` | persistence | SQLAlchemy ORM. The only place a table is declared. |
| `query.py` | persistence | Reusable SQL expression fragments. No session, no I/O. |
| `crud.py` | persistence | The **only** file that opens a `Session` against its own tables. Returns schemas/DTOs, never ORM rows. |
| `serializers.py` | persistence | ORM ↔ schema transformation, both directions. Called by `crud` at its edges. |
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

`subscribers.py` is deliberately absent from that list. A module with subscribers
publishes `subscriber_registry.py` and the entrypoints import *that* — which is
what makes "registered in the API but not the worker" a diff in one file instead
of a silent mismatch between two, and what keeps the file that happens to hold
the handlers today free to be split tomorrow.

`subscriber_registry.py` is also where a module declares its **reconciliation
nets**. A durable subscriber derives state from an event, and delivery is
at-least-once but never guaranteed — a bus consumer can drop a message, and some
write paths publish no event at all. So each durable subscriber declares an
`infra.jobs.reconciliation.DurableSubscriberNet`: either the scheduled backfill
that re-derives what the create path missed, or the reason none is needed.
`tests/architecture/test_reconciliation_nets.py` holds every module to it.

The type lives in the platform rather than in the module that needed it first.
While it lived in `modules/activities`, the invariant was enforceable for exactly
one module — declaring nets anywhere else would have meant importing the
activities module to borrow the vocabulary, a dependency between two bounded
contexts for the sake of a shared word. Followers registered two durable
subscribers with no net, no exemption, and nothing to catch it.

A module-level file (not inside a sub-package) is the right home for a surface
that belongs to the whole module rather than one aggregate —
`modules/activities/computation.py`, the pure metric maths the parsers, the
Strava adapter and the migrations all use.

### 2. Module-internal — importable by sibling sub-packages, not by other modules

`service.py` — the owning package's application layer, and how a sibling reaches
its data. A derived subsystem that needs the activity row asks `activity.service`,
not `activity.crud`; otherwise every subsystem becomes a second owner of the
table.

`query.py` — SQL expression fragments. Shared because the rules those queries must
agree on (above all *which local day did this happen on?*) must have one
definition, and because a fragment opens no session and fetches no rows.

Plus the named intra-module seams a module declares (for activities:
`activity/child_access.py`, `activity/ingestion_service.py`).

### 3. Package-private — importable only from inside its own sub-package

`crud.py`, `models.py`, `serializers.py`, `utils.py`, `subscribers.py`,
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

Four entries deserve the reasoning:

- **`crud` never calls another module.** A `SELECT` that first has to ask another
  bounded context a question is a service-layer decision wearing a persistence
  layer's clothes.
- **`models` may cross boundaries.** SQLAlchemy relationships share one registry,
  so `Activity` ↔ `Gear` ↔ `Users` must name each other. These are `TYPE_CHECKING`
  imports describing a foreign key, not a behavioural reach.
- **`integration_service` may read its own module freely.** It *is* the module,
  presenting a narrow face outward.
- **A read model may select from the table it projects.** `activity_summaries`
  aggregates the activities table and imports its ORM class to do so. Ownership is
  a rule about *writes*; a package that only reads is not a second owner.

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

## Sharing a shape between sibling packages

When several sub-packages are the same operation over different rows, the
operation lives once in the owning package and each sibling *declares itself*
rather than reimplementing it. `activity/child_collection.py` is the worked
example: laps, sets and workout steps each state their hide flag, their two CRUD
calls and their page type, and the shared seam runs the read — the access gate,
the paging, and the rule that a refusal and an empty collection answer alike.

The test for whether something belongs in such a seam is not "is this repeated?"
but "would a divergence here be a bug?". Three copies of a docstring are
harmless; three copies of an access decision are three chances to get it wrong,
and two of the copies had already drifted before this was extracted.

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

It checks module-level files too, not just sub-package ones — which is the whole
surface of a flat module. Without that, `modules.followers.crud` was importable
from anywhere: the dotted path has no sub-package segment to match on, so every
rule silently skipped it.

It resolves each `from x.y import z` against the filesystem rather than counting
dots. The dot-count heuristic it replaced could not tell a submodule from a
symbol in a flat module — `modules.followers.constants` has the same depth as a
sub-packaged module's `modules.activities.activity` — so every symbol imported
from a flat module was misread as a package reach.

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

**Resolved.** `activity_thumbnail`, `activity_geocoding` and `activity_media` read
the activity row and its streams through `activity.service` and
`activity_streams.service`. The child CRUDs no longer join the activities table
to filter rows by owner — the parent package scopes the ids and hands each child
a plain list.

Two reaches into `activity/` remain, both stated rather than deferred:
`activity_streams.crud` joins the parent for `total_timer_time` (a column, not a
permission), and `activity_summaries` projects the activities table, which is the
read-model rule above.

### Provider cycle

**Resolved.** `activity_ingestion` no longer imports `modules.strava` or
`modules.garmin`; the `activities-provider-agnostic` contract forbids the whole
module from doing so. Providers register on `provider_registry`, subclass
`BulkImportSource`, and resolve their own synced gear before handing a file to
ingestion.

### Platform → domain inversion

**Resolved.** `core/scheduler.py` schedules what it is handed and imports no
module; `core/i18n` owns the locales it ships a catalog for instead of reading
the users module's `Language` enum. The `core-not-domain` contract enforces it,
with one recorded exception: `core.middleware` reads the server-settings *schema*
— a data shape, not behaviour — to type what it stamps onto the request.

The locale list now exists three times on purpose: `core.i18n` (what we can write
an email in), the `Language` enum (what a client may pick), and the shipped
catalog directories. `tests/core/test_i18n.py` asserts all three agree, so drift
fails CI rather than silently falling back to English.

### Providers feeding ingestion

**Resolved.** `activity_ingestion/integration_service.py` publishes the entry
point and the source types. Providers import one module; `bulk_entry` and
`sources` are package-private again.

### Persistence layers calling other modules

**Resolved for activities.** No `crud`, `query`, `serializers` or `utils` file in
the module asks another bounded context a question. The values those queries need
are resolved by the layer above and passed in: `followee_ids` on the visibility
filter, the shareable-links policy in `activity.service` / `activity.child_access`,
and the max-heart-rate lookup in `activity_streams.service`. Enforced by the
`activities-persistence-asks-nothing` contract.

The other modules still do it — `health.*.crud` reaching `users.users.utils`,
`notifications.utils` reaching `users` and `websocket`, and so on. Each is fixed
as its module is converted.

### Subscribers reaching past a module surface

**Resolved for followers.** `followers.subscribers` imported
`notifications.utils`, `websocket.manager` and `websocket.utils` — three reaches
past two modules' surfaces to do what `notifications.integration_service` and
`websocket.integration_service` each state as one operation, and the reason the
module could not be lifted out without dragging the websocket connection registry
with it. Enforced by `followers-consumes-surfaces`.

The same reach survives in `garmin`, `strava`, `auth.sign_up_tokens` and
`users.users_profile`; each is fixed as its module is converted.

### Migration → internals

`app/migrations/migration_*.py` import `activity.crud`, `activity_streams.crud`,
`activity_media.crud`, `activity_file_import.utils` and `activity_thumbnail.render`.
Data migrations are pinned to the schema of their era, so routing them through a
surface that evolves would break them; they are exempt by nature, and the exemption
is recorded rather than assumed.
