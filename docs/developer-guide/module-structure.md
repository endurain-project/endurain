# Module Structure

This guide defines the structure every backend module follows and the rules that
make each module **replaceable**. A module can move to another distribution, or
be replaced by another implementation, because callers import only surfaces the
module deliberately publishes.

`modules/activities` is a composition namespace containing several independent
modules (`activity`, `activity_laps`, `activity_streams`, and so on).
`modules/followers` is the reference for a module that stays flat. Every other
module, and every new module, is converted to one of these shapes.

## The two units

| Unit | What it is | Example |
| --- | --- | --- |
| **Composition namespace** | Groups related modules and collects their routers, jobs and subscribers. It is not an implementation boundary. | `modules/activities` |
| **Module** | One aggregate or capability and the unit of extraction. | `modules/activities/activity_laps`, `modules/followers` |

A bounded context with one aggregate stays flat (`modules/followers`). Related
activity capabilities share the `modules.activities` namespace, but each child
package remains its own module. They are **peers**, not implementation friends:
`activity_thumbnail` may consume `activity_streams.integration_service`, but it
may not import `activity_streams.service`, CRUD, ORM models, signing, or helpers.

The root `activity` package owns the activity row and parent access decisions. It
does not own child tables merely because they refer to `activities.id`.

## File roles

Filenames are part of the contract: the enforcement rules match on them, so a
file named `crud.py` is treated as persistence wherever it appears.

The corollary is that a misnamed file is *silently exempt*. `activity_ingestion`
held its persistence in `ingestion_jobs_crud.py`, which no `modules.activities.*.crud`
wildcard matched — so the one CRUD module in the tree that routers were free to
import was the one nobody had noticed was named wrong. Renaming it to `crud.py`
brought it under four existing contracts without writing a new one.

A stem may **qualify** a role, and it inherits every rule that role carries:
`summary_crud.py` is a `crud`, `summary_router.py` is a `router`. This is not a
convenience — it is the same exemption one level down. The activity summaries
feature shipped its aggregations in `summary_query.py`, a file that opened a
`Session` and executed while matching neither the `crud` rules (wrong stem) nor
the `query` ones (wrong role), and `summary_router.py` had to be hand-added to a
public-names list to be importable at all. A package that genuinely needs a
second persistence module names it `<thing>_crud.py`; it does not invent a new
word. The vocabulary lives once in `tests/_helpers/module_roles.py`, because two
copies of "what does this filename mean?" is the drift the rule exists to stop.

Because the role is what the rules see, the role has to be the truth:
`tests/architecture/test_module_boundaries.py` asserts that only a `crud`-role
file executes statements against the session. Transaction control (`commit`,
`flush`, `rollback`) is excluded — that belongs to the service that owns the
boundary.

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
| `contributors.py` | **namespace contract** | Typed callbacks installed by app composition for generic ingestion/profile orchestration. |
| `scheduled_jobs.py` | **module surface** | The module's recurring jobs, collected by the composition root. |
| `model_registry.py` | **composition surface** | Declares the package's ORM model module without requiring core to scan domains. |
| `migration_service.py` | **migration-only surface** | Version-pinned operations used by `app/migrations`; never an ordinary domain dependency. |

Anything else (`utils.py`, `signing.py`, `render.py`, `pipeline.py`, …) is
package-private by default.

## Visibility

Four classes. This is the whole rule.

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

Every name on `integration_service.py` is a promise, so it holds only operations
with a real caller. The child packages each grew six public functions where two
were reached from outside: the contributor plumbing (`store_laps`,
`restore_profile_records`, `list_laps_for_activities`) sat next to the
contributor factory that was the actual surface, so "what may I depend on?"
answered with three times more than the module meant. A new operation lands there
with the caller that needed it, or stays private until then;
`test_the_surface_holds_only_operations_with_callers` fails on the difference.

A surface function that only forwards its arguments is not a layer either. The
thumbnail and geocoding subsystems reached the activity row through
`integration_service` → `service` → `crud`, where the middle call added no
decision, no access check and no transaction — three files to change to add an
argument. Those go straight to CRUD, which the matrix below already permits; what
belongs in `service` is the *arrangement* of a write (stage, publish, commit),
not the act of forwarding.

`subscribers.py` is deliberately absent from that list. A module with subscribers
publishes `subscriber_registry.py` and the entrypoints import *that* — which is
what makes "registered in the API but not the worker" a diff in one file instead
of a silent mismatch between two, and what keeps the file that happens to hold
the handlers today free to be split tomorrow.

`modules.auth` is the one module whose behavioural surface is not called
`integration_service.py`. It publishes `identity_service.py` (plus
`dependencies.py`), because its boundary is not "what may you call?" but "what
may you learn about the caller?" — a distinction the
[auth boundary guide](auth-boundary.md) states and a dedicated `auth-boundary`
contract enforces structurally. The inconsistency is real and is the cost of
that: `auth` answers "what may I depend on?" with a different filename than
every other module. It is recorded here rather than smoothed over, and no other
module may follow it.

`subscriber_registry.py` is also where a module declares its **reconciliation
nets**. A durable subscriber derives state from an event, and delivery is
at-least-once but never guaranteed — a bus consumer can drop a message, and some
write paths publish no event at all. So each durable subscriber declares a
`jasil.jobs.reconciliation.DurableSubscriberNet`: either the scheduled backfill
that re-derives what the create path missed, or the reason none is needed.
`tests/architecture/test_reconciliation_nets.py` holds every module to it.

The type lives in the platform rather than in the module that needed it first.
While it lived in `modules/activities`, the invariant was enforceable for exactly
one module — declaring nets anywhere else would have meant importing the
activities module to borrow the vocabulary, a dependency between two bounded
contexts for the sake of a shared word. Followers registered two durable
subscribers with no net, no exemption, and nothing to catch it.

A namespace-level file is appropriate only for composition or a genuinely
shared, dependency-free contract. `modules/activities/computation.py` is the
pure metric maths used by parsers and provider adapters; it owns no table and
calls no module. `modules/activities/contributors.py` defines the dependency-free
activity ingestion/profile callback contracts, while `contributor_registry.py`
stores only the contributors explicitly installed by `app/module_registry.py`.
Child packages return contributor objects from `integration_service.py`; package
imports never register themselves as a side effect.

### 2. Composition surface — imported only while assembling the application

`router.py`, `public_router.py`, `dependencies.py`, `subscriber_registry.py`,
`scheduled_jobs.py`, and `model_registry.py` are collected by `api.py`, `main.py`,
`worker.py`, Alembic, or the namespace-level activities registries. Business
modules do not call them.

Every persistence-owning package declares its model module in
`model_registry.py`. `app/model_registry.py` collects converted modules
explicitly. Its filesystem scan exists only for unconverted legacy modules and
shrinks as those modules adopt this structure. `core.database` never discovers
or imports domain models.

### 3. Migration-only surface — imported only by `app/migrations`

`migration_service.py` exposes the exact historical operations a versioned data
migration still needs. It prevents an old migration from reaching arbitrary CRUD,
parser, render, or signing internals while keeping that migration pinned to its
era. Import-linter forbids domain and core code from consuming it.

### 4. Package-private — importable only from inside its own module

`service.py`, `query.py`, `crud.py`, `models.py`, `serializers.py`, `utils.py`,
`signing.py`, `subscribers.py`, `event_publishers.py`, and every unlisted helper.
Sibling activity modules are outside callers for this rule. A derived subsystem
that needs the activity row asks `activity.integration_service`, never
`activity.service` or `activity.crud`.

`__init__.py` holds a docstring and **nothing else**. A re-export facade would
hand out ORM models and CRUD functions under a package path, which is a silent
bypass of every rule above.

## Allowed-import matrix

Read as *row imports column*.

| From ↓ / To → | own `crud` | own `service` | peer `integration_service` | peer internals | peer `schema`/`contracts` | other module |
| --- | --- | --- | --- | --- | --- | --- |
| `router` | ✗ | ✓ | ✗ | ✗ | ✓ | transport dependencies only |
| `service` | ✓ | — | ✓ | ✗ | ✓ | `integration_service` only |
| `crud` | — | ✗ | ✗ | ✗ | ✓ | ✗ |
| `models` | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| `subscribers` | ✗ | ✓ | ✓ | ✗ | ✓ | `integration_service`/events only |
| `integration_service` | ✓ | ✓ | ✓ | ✗ | ✓ | `integration_service` only |
| `app/migrations` | ✗ | ✗ | ✗ | ✗ | ✓ | `migration_service` only |

Three entries deserve the reasoning:

- **`crud` never calls another module.** A `SELECT` that first has to ask another
  bounded context a question is a service-layer decision wearing a persistence
  layer's clothes.
- **`models` do not import other models.** A foreign key names a table with a
   string (`ForeignKey("activities.id")`). Database `ON DELETE` actions own
   lifecycle behavior. Unused bidirectional ORM relationships would force every
   optional package to be imported before any mapper could configure.
- **`integration_service` may read its own module freely.** It *is* the module,
  presenting a narrow face outward.

A face is not a layer, which is the one thing that entry does **not** license. A
write has an arrangement — stage the rows, publish the fact, own the commit that
makes those atomic — and that arrangement belongs to `service`. The root activity
surface was doing it both ways: `bulk_set_activities_gear`,
`delete_all_strava_activities` and `delete_all_activities_for_user` each called
CRUD with `commit=False`, published their own events and handed over `db.commit`,
so the module had two write-orchestration layers and which one a write went
through depended only on whether it was reached from a route or from another
module. The `activities-surfaces-delegate-writes` contract forbids an
`integration_service` from importing `event_publishers`: a surface that cannot
publish cannot own the commit that has to be atomic with the publish, which
leaves calling its own service as the only way to arrange a write.

## Layering inside a module

```
router / public_router  →  service  →  crud  →  query / models
                              ↓
                     event_publishers → events
```

Downward only. `crud` never calls `service`; `service` never touches `models`.

## What a module may depend on

- **`core.*`** — cross-cutting primitives (logging, config, pagination, exceptions,
  timezone, signing, uploads). Always allowed.
- **`jasil.*`** — the platform substrate, an external package. Through its public
  surface only: `jasil.providers` (the capability ports), `jasil.publisher`,
  `jasil.events`, `jasil.subscribers`, `jasil.jobs.registry`. Never
  `jasil.backends` (the adapters), `jasil._core`, or a `crud` module.
- **Other modules** — through their `integration_service` only.
- **`fastapi`** — routers and dependencies only. Persistence raises
  `core.exceptions`; the app's error handler maps those to responses.

The dependency direction is fixed: `core` and the substrate must never import
`modules`. A module publishes its scheduled work (`scheduled_jobs.py`), its
subscribers (`subscriber_registry.py`) and its plug-ins; the platform *collects*
them. It is never the platform's job to know a module exists.

Because the substrate is an external package, that rule is split across two
enforcement points. Its own internal direction (ports never importing adapters,
nothing importing `modules`) is an import contract in the JASIL repository,
verified on its releases. Which part of it *this* application may touch lives in
`tests/architecture/test_jasil_boundary.py` — import-linter cannot state it,
because it rejects a subpackage of an external package as a forbidden module.

## Inverting a platform-to-domain reach

When the platform appears to need something from a module, the module registers
it rather than the platform importing it. Three worked examples live in the tree:

| Reach | Inversion |
| --- | --- |
| The scheduler needed each module's recurring jobs | Each module declares `scheduled_jobs.recurring_jobs()`; `main.py` collects and hands the list to `start_scheduler`. |
| Ingestion needed to pull from Strava and Garmin | Providers call `activity_ingestion.integration_service.register_activity_provider`; the private registry names no provider. |
| Bulk import needed Strava-export semantics | `BulkImportSource` is a base class; `modules.strava.bulk_import_source.StravaBulkImportSource` subclasses it. |
| Activity ingestion/profile restore needed child records | Each child returns typed contributor objects from `integration_service`; `app/module_registry.py` installs them in `activities.contributor_registry`. |
| Serializing an activity needed its thumbnail's URL | `activity` asks `contributor_registry.resolve_thumbnail_url`; `activity_thumbnail` registers the resolver at composition time. |

The shape is always the same: the lower layer owns the *seam* (a registry, a base
class, a protocol), the higher layer owns the *implementation*, and a composition
root (`main.py`, `worker.py`) connects them. A registration performed in one
entrypoint must be performed in the other — a provider or subscriber registered
in the API but not the worker silently does nothing wherever its work is claimed.

## Sharing behavior between peer modules

When several modules perform the same operation over different rows, the
operation lives once in its owning module and peers consume its public behavior.
`activity/child_collection.py` is the worked example: the root activity package
owns the parent access rule and publishes `ChildCollection` through
`activity.integration_service`. Laps, sets and workout steps state their hide
flag, CRUD calls and page type without importing the private helper file.

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
activity module inherits every cross-module rule the day it is created, instead
of when someone remembers to add it to a list. A separate contract prevents
domain/core code from consuming `*.migration_service`.

**`backend/tests/architecture/test_module_boundaries.py`** — the one rule
import-linter cannot express. A `forbidden` contract rejects an import if *any*
source matches *any* forbidden module, so "a package may import its own `crud`
but not a peer's" is not statable: the wildcard pair
`modules.activities.* → modules.activities.*.crud` also rejects
`activity_laps.service → activity_laps.crud`. The conformance test walks the AST,
compares each import against the importer's own package, and consults an explicit
allowlist containing only composition edges and exact read-model projections.

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
and why it exists. It may not be used for service, CRUD, model, query, signing,
parser, or storage access that belongs behind an integration surface.

The same file holds the rule about *direction*. Every rule above asks what one
package may reach for in another; none of them notices when the reaching goes
both ways, and two packages that import each other are one package pretending to
be two. So the package-level import graph inside a module is asserted to be a
DAG. A derived subsystem depends on the thing it derives from, never the reverse;
when the depended-on package needs something back, it states a seam and
composition installs the answer.

## Adding a module

1. Create either `modules/<name>` or a package under a composition namespace such
   as `modules/activities/<name>`; `__init__.py` contains a docstring only.
2. Add `integration_service.py`. It is the sole behavioral import path for peers
   and outside modules; keep it limited to operations with real callers.
3. Add `model_registry.py` when the module owns a table, and add its contribution
   to the namespace/application model registry.
4. Add `migration_service.py` only when an existing data migration needs a
   version-pinned private operation.
5. Add `subscriber_registry.py` if the module has subscribers; register it in both
   `main.py` **and** `worker.py`.
6. Add `scheduled_jobs.py` if the module has recurring work; add it to the list
   `main.py` hands to `start_scheduler`.
7. For an activity child parsed or archived as JSON, add the applicable
   `ingestion_contributor`, `profile_contributor`, or
   `profile_global_contributor` factory to `integration_service.py`, then register
   that factory in `app/module_registry.py`. Do not register at import time.
8. Add the module to the source lists of the cross-module contracts in
   `backend/.importlinter`.
9. Add a new top-level bounded context to `_CONVERTED` in
   `backend/tests/architecture/test_module_boundaries.py`
   and in `backend/tests/test_logging_rule.py`.

## Known debt

Tracked here so it is visible rather than discovered. Each item is enumerated in
the conformance test's allowlist.

### Sibling persistence reaches

**Resolved.** `activity_thumbnail`, `activity_geocoding` and `activity_media` read
the activity row and streams through `activity.integration_service` and
`activity_streams.integration_service`. Child CRUDs no longer join the
activities table to decide access.

No reach into `activity/` remains. `activity_streams.crud` used to join the
parent for `total_timer_time`; the value now arrives as a field on the
`ActivityScoringContext` that `activity_streams.service` resolves through the
root surface, so the persistence layer is handed the column rather than fetching
it. Both allowlists in the conformance test are consequently empty.

### Root package depending on a child
**Resolved.** `activity/serializers.py` imported
`activity_thumbnail.integration_service` to turn a stored thumbnail key into a
URL, while `activity_thumbnail/service.py` imported `activity.integration_service`
to read the row it derives from. Both used the other's published surface, so
every visibility rule was satisfied and the pair still could not be built,
tested or lifted out separately.

The root now asks `contributor_registry.resolve_thumbnail_url` and the thumbnail
package registers the answer from `app/module_registry.py`, which leaves
`activity` a sink in the package graph — nothing inside `modules.activities`
imports out of it. `TestPackageIndependence` fails on any cycle, and
`test_module_registry.py` asserts the resolver is actually installed, because a
missing registration is not an import error: it is a null thumbnail URL on every
activity in the API.

### Provider cycle

**Resolved.** `activity_ingestion` no longer imports `modules.strava` or
`modules.garmin`; the `activities-provider-agnostic` contract forbids the whole
module from doing so. Providers register through
`activity_ingestion.integration_service`, subclass `BulkImportSource`, and
resolve their own synced gear before handing a file to ingestion.

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

`modules/activities/computation.py` is the counter-case, and stays where it is.
It is pure, imports no module, and three consumers need the same numbers — the
file parsers, the Strava adapter and the data migrations — so a second copy in
Strava would be two definitions of normalized power that could disagree. Moving
it to `core` would be the same inversion in reverse: pace and normalized power
are fitness-domain maths, not platform primitives, and `core` would then hold
domain knowledge that no contract would catch, because `core` importing nothing
is exactly what the rule checks for.

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

**Resolved.** `app/migrations/migration_*.py` consume package-owned
`migration_service.py` adapters. The blanket migration allowlist is gone, and
import-linter prevents ordinary domain/core code from using those adapters.

### ORM registry and cross-package relationships

**Resolved for activities and followers.** Their models use scalar foreign keys
and database `ON DELETE` behavior rather than unused bidirectional ORM
relationships. Each persistence package declares its model module through
`model_registry.py`; `app/model_registry.py` composes converted modules, and
`core.database` performs no domain scan. The app-level legacy scan remains only
for modules not converted yet.
