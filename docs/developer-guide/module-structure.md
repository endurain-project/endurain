# Module Structure

This guide defines the structure every backend module follows and the rules that
make each module **replaceable**. A module can move to another distribution, or
be replaced by another implementation, because callers import only surfaces the
module deliberately publishes.

`modules/activities` is a composition namespace containing several independent
modules (`activity`, `activity_laps`, `activity_streams`, and so on).
`modules/followers` is the reference for a module that stays flat. A new module
follows one of these shapes; the existing modules are converted one at a time as
they are reworked (see [Known debt](#known-debt)).

## Rules at a glance

The sections below are the authority; this is the part to keep in your head.

- A file's name is its role; `__init__.py` is a docstring and nothing else.
- Peers call only another module's `integration_service`, `contracts`, `schema`, `constants` and `events`.
- `crud` stages (`flush`); `service` commits and publishes. A surface write stages and its caller commits, unless listed.
- Providers and `core.config` are resolved at entry points and passed down.
- Derived work is an event subscriber with a reconciliation net; delivery is at-least-once.
- How code must *run* (transactions, claims, threads, storage lifecycle, bounded scans) is in
  [Runtime behaviour](#runtime-behaviour).

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
file named `crud.py` is treated as persistence wherever it appears. The
corollary is that a misnamed file is *silently exempt* from every rule, which is
why a file's name has to be the truth.

A stem may **qualify** a role and inherits every rule that role carries:
`summary_crud.py` is a `crud`, `summary_router.py` is a `router`. A package that
needs a second persistence module names it `<thing>_crud.py`; it does not invent
a new word. The vocabulary lives once in `tests/_helpers/module_roles.py`.

Because the role is what the rules see, the role has to be the truth:
`tests/architecture/test_module_boundaries.py` asserts that only a `crud`-role
file executes statements against the session, that only `router`/`public_router`
files construct an `APIRouter`, and that only `models` files declare ORM classes.
The vocabulary is deliberately open (`render.py` and `signing.py` are legitimate
private helpers), so the check is that a file's *content* agrees with its name
rather than that its name is on a list. Ending a transaction (`commit`,
`rollback`) is a separate rule, stated under
[Transaction ownership](#transaction-ownership).

| File | Layer | Responsibility |
| --- | --- | --- |
| `models.py` | persistence | SQLAlchemy ORM. The only place a table is declared. |
| `query.py` | persistence | Reusable SQL expression fragments. No session, no I/O. |
| `crud.py` | persistence | The **only** file that opens a `Session` against its own tables. Stages writes (`flush`), never commits or rolls back. Returns schemas/DTOs, never ORM rows. |
| `serializers.py` | persistence | ORM ↔ schema transformation, both directions. Called by `crud` at its edges. |
| `service.py` | application | Decides access, orchestrates, publishes events, owns transaction boundaries. |
| `router.py` / `public_router.py` | transport | Validate, delegate to `service`, return. No domain rule. |
| `dependencies.py` | transport | FastAPI DI and typed request-parameter aliases (`Annotated[int, Path(gt=0)]`, enums); validation is declared on the type, not raised by hand. |
| `schema.py` | contract | Pydantic request/response shapes. Serialized to clients. |
| `contracts.py` | contract | Inter-module DTOs and typed seams. Never serialized. |
| `constants.py` | contract | Domain constants and mapping tables. |
| `events.py` | contract | Event-type names and validated payload models. |
| `event_publishers.py` | application | Publishes this package's domain events. |
| `subscribers.py` | application | Handles events. Registered from `subscriber_registry`. |
| `integration_service.py` | **module surface** | The curated set of operations other modules may call. |
| `contributors.py` | **namespace contract** | Typed callbacks installed by app composition for generic ingestion/profile orchestration. |
| `scheduled_jobs.py` | **module surface** | The module's recurring jobs, collected by the composition root. |
| `subscriber_registry.py` | **composition surface** | Registers the package's bus subscribers and durable handlers and declares its reconciliation nets; the entrypoints import this, never `subscribers.py`. |
| `contributor_registry.py` | **composition surface** | Process-local store of the contributors and resolvers that `app/module_registry.py` installs. Names no package. |
| `computation.py` | **namespace helper** | Pure computation shared by a namespace's packages. Owns no table and calls no module. |
| `model_registry.py` | **composition surface** | Declares the package's ORM model module without requiring core to scan domains. |
| `migration_service.py` | **migration-only surface** | The only domain surface `app/migrations` may import; never an ordinary domain dependency. |

Anything else (`utils.py`, `signing.py`, `render.py`, …) is package-private by
default. A helper that orchestrates other modules or ends a transaction is not a
helper: it plays the `service` role and is named `<thing>_service.py`, such as
`activity_ingestion/pipeline_service.py`.

## Visibility

Four classes. This is the whole rule. Each file name appears in exactly one.

### 1. Module surface — importable by peers and outside modules

| Surface | Purpose |
| --- | --- |
| `integration_service.py` | Behaviour. Every cross-module call goes through it. |
| `contracts.py` | The data shapes that surface accepts and returns. |
| `schema.py` | Client-facing shapes, when a consumer genuinely needs the wire type. |
| `constants.py` | Stable domain constants. |
| `events.py` | Event names and payloads, so a consumer can subscribe. |
| `dependencies.py` | FastAPI DI, mounted at the HTTP boundary (transport code only). |

Every name on `integration_service.py` is a promise, so it holds only operations
with a real caller **outside its package**. Contributor plumbing
(`_store_laps`, `_list_laps_for_activities`) stays private; the contributor
factory is the surface. A new operation lands there with the caller that needed
it, or stays private until then;
`test_the_surface_holds_only_operations_with_callers` resolves callers by AST and
fails on the difference. A package nothing outside calls (`activity_geocoding`)
has no `integration_service.py` and is listed with its reason in
`_NO_CROSS_MODULE_SURFACE`.

A surface function that only forwards its arguments is not a layer either. When
`integration_service` → `service` → `crud` adds no decision, no access check and
no transaction, the surface goes straight to CRUD, which the matrix below
permits. What belongs in `service` is the *arrangement* of a write (stage,
publish, commit), not the act of forwarding. A read-only surface function calls its
own `crud` directly; a `service` function added only to forward is the layer this
paragraph rules out.

`subscribers.py` is private (class 4). A module with subscribers publishes
`subscriber_registry.py` (class 2) and the entrypoints import *that*, so
"registered in the API but not the worker" is a diff in one file, and the file
that holds the handlers can be split without touching the entrypoints.

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

The `DurableSubscriberNet` type lives in the platform (`jasil`), not in a module,
so every module can declare nets without importing another bounded context for a
shared word.

A namespace-level file is appropriate only for composition or a genuinely
shared, dependency-free contract. `modules/activities/computation.py` is the
pure metric maths used by parsers and provider adapters; it owns no table and
calls no module. `modules/activities/contributors.py` defines the activity
ingestion/profile callback contracts (it depends only on the activity schema), while `contributor_registry.py`
stores only the contributors explicitly installed by `app/module_registry.py`.
Child packages return contributor objects from `integration_service.py`; package
imports never register themselves as a side effect.

### 2. Composition surface — imported only while assembling the application

`router.py`, `public_router.py`, `subscriber_registry.py`, `scheduled_jobs.py`,
and `model_registry.py` are collected by `api.py`, `main.py`, `worker.py`,
Alembic, or the namespace-level activities registries. Business modules do not
call them. `scheduled_jobs.py` also holds the job runners.

Every persistence-owning package declares its model module in
`model_registry.py`. `app/model_registry.py` collects converted modules
explicitly. Its filesystem scan exists only for unconverted legacy modules and
shrinks as those modules adopt this structure. `core.database` never discovers
or imports domain models.

### 3. Migration-only surface — imported only by `app/migrations`

`migration_service.py` exposes the operations a versioned data migration still
needs, and nothing else. It stops a migration reaching arbitrary CRUD, parser, render
or signing internals, and gives the migration one place to find the commit that CRUD no
longer performs. Import-linter forbids domain and core code from consuming it.

It is a boundary, **not a snapshot**: most entries alias live code, so changing a
parser or a CRUD function changes what a historical migration does. A data migration
that must stay byte-for-byte reproducible is rewritten in plain SQLAlchemy Core against
the tables as they were at that revision, and stops importing `modules.*`; the
wrapper is not a substitute for that.

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
makes those atomic — and that arrangement belongs to `service`. An
`integration_service` therefore never publishes events or ends a transaction: it
calls its own `service` for any write that decides, and
`test_a_surface_does_not_publish_events` forbids it from importing
`event_publishers` in every converted module. A surface that cannot publish cannot own the commit that has
to be atomic with the publish, so there is one write-orchestration layer, not two.

## Layering inside a module

```
router / public_router  →  service  →  crud  →  query / models
                              ↓
                     event_publishers → events
```

Downward only. `crud` never calls `service`; `service` never touches `models`.

## Transaction ownership

`service` owns the transaction; `crud` only stages. The unit of work is known to
the layer that arranges it, not to the single statement a `crud` function runs.

| Layer | Does | Never does |
| --- | --- | --- |
| `crud` | `add` / `execute`, then `flush()` so constraint violations and row counts surface at the call; `refresh` after the flush when it needs server defaults | `commit()`, `rollback()`, a `commit` parameter |
| `service` | Stages through `crud`, publishes through `event_publishers` (passing `db.commit` so row and outbox event commit together), or calls `db.commit()` itself when no event is involved | — |
| `integration_service` | Stages through its own `crud` for a [decision-free write](#decision-free-surface-writes), or calls its own `service` for a write that decides or publishes | End the caller's transaction, unless it is a [listed unit of work](#surface-writes-stage-the-caller-commits); publish directly |
| entry point (`get_db`, a job, a subscriber) | Rolls back what its caller left open | — |

Two choices in that table are deliberate:

- **No `commit` flag.** A `commit: bool = True` parameter keeps two code paths in
  every writer, and its default is the wrong one: `service` always passed
  `commit=False`, so the `commit=True` branch was exercised only by tests. A
  writer that can end its own transaction also makes "stage, publish, commit"
  depend on each caller remembering to opt out. A writer that cannot, cannot be
  misused.
- **`crud` does not roll back.** A rollback decides the fate of everything the
  session staged, which `crud` does not know. A `crud` function never calls
  `rollback()` itself; it raises, and the transaction owner
  (`core.database.get_db` on a request, the job or subscriber that opened the
  session elsewhere) rolls back.

  One accepted exception: `@handle_db_errors`, which wraps `crud` functions,
  rolls the whole session back on a database error and on an escaping
  `IntegrityError`. That is the same decision made implicitly, and it is kept
  only because unconverted modules still rely on it. A `crud` that translates
  `IntegrityError` into a `ConflictError` itself is not rolled back by it. Do not
  add new reliance on the decorator's rollback; the transaction owner is
  responsible, and the decorator's rollback is removed when the last unconverted
  module is converted.

### Surface writes stage, the caller commits

A cross-module call must not end the caller's transaction. A caller that composes
two surface calls needs them atomic, and a module that can commit another
module's session can persist half of an operation it does not own. So a surface
write **stages** (`flush`) and its caller, which holds the session and knows the
unit of work, commits. `set_thumbnail_key`, `clear_all_thumbnail_keys` and
`set_activity_location` work this way; their callers (the thumbnail and geocoding
services) commit.

The exception is a surface operation that is a self-contained unit of work, and
the reason is always one of two:

- It **publishes an event** that has to be atomic with the change. The platform
  publisher takes the commit callable because in the durable path the outbox row
  is staged in the transaction and committed with it, and in the best-effort path
  the commit must come before the dispatch. A surface that publishes therefore
  owns the commit ordering, through its own `service`.
- It **owns a rollback**: a race on a unique key leaves the session unusable
  until it is rolled back, so the write must roll back before it looks up the
  winner.

Each such operation is listed in `_SURFACE_UNITS_OF_WORK` with its reason.
`TestSurfaceTransactions` follows every surface function through its own
`service` and helpers and fails on one that ends a transaction without being
listed, and on a listed one that no longer does.

### Decision-free surface writes

An `integration_service` function may stage through its own `crud` only when the
write makes no decision: no access check, no invariant beyond payload shape, no
event and no commit. The contributor `persist` and `restore` callbacks are the
case this exists for. The caller (ingestion in `activity`, the profile importer)
owns the unit of work, so a `service` function between them could only forward
and stage, which is a layer that adds nothing.

The moment such a write needs an ownership check, a business rule, an event or a
commit, it moves to `service`. The surface never grows a second write path beside
it.

A failed `commit()` is not translated in `service`. `service` does not wrap its
commit in `try`/`except`, and it does not catch `SQLAlchemyError`. The error
propagates, `core.database.get_db` rolls the session back, and
`core.exceptions.database_error_handler` — registered once with the other
handlers — renders the same opaque 500 problem document a `ProcessingError`
produces. Translating at one boundary keeps the rule in one place instead of one
`try` per service, and keeps the SQL statement and its parameters out of both the
response and the log message (OWASP A09). A service catches a database error only
to make a *domain* decision from it — mapping `IntegrityError` to `ConflictError`
is the precedent — never to re-raise a generic one.

`test_crud_does_not_end_transactions` enforces it: a `crud`-role file in a
converted module may not call `commit` or `rollback`. Files that still do are
listed in `_CRUD_TRANSACTION_DEBT`, and the test fails on an entry that no longer
offends so the register shrinks rather than lingers.

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

Providers are resolved at the edge and passed down. A router declares
`Depends(core.dependencies.get_storage)`; a subscriber, scheduled job or
`integration_service` surface function (callers with nothing to carry a provider)
calls `jasil.runtime.get_active_platform()` once and hands the provider to
`service`. A `service`, `crud` or helper never resolves it itself:
`TestProviderResolution` fails on `get_active_platform` below an entry point, so
a dependency is visible in the signature and a test substitutes it without
patching the runtime.

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

## Extraction target

"Could become its own library" means a specific thing here, and it is worth
stating so the next module is converted to the same target:

- **In scope:** a module is a package that could be installed separately and run
  **in the same process against the same database**. Its only inbound surface is
  the published one; it declares its own models, jobs, subscribers and
  contributors; and a peer can be lifted out without editing another module's
  internals.
- **Accepted, not accidental:** surface operations take a SQLAlchemy `Session`
  (`list_accepted_followee_ids(user_id, db)`). Callers share one transaction,
  which is what makes "stage, publish, commit" atomic across a module boundary.
  This is also why a module cannot yet move to another *process*.
- **Out of scope:** swappable implementations behind Protocol ports. Use a port
  only for a seam that genuinely has several implementations — providers,
  geocoding, file storage — and let the consumer own the Protocol. Everywhere
  else the concrete peer `integration_service` is the contract.
- **Still shared:** the metadata (`core.database.Base`) and the central Alembic
  history. A module will need its own migration branch before it can be
  distributed on its own.

## Choosing a coupling mechanism

| Need | Mechanism | Example |
| --- | --- | --- |
| Ask a peer a question, or read its data | Call its `integration_service` | `followers.integration_service.list_accepted_followee_ids` |
| A write that must be atomic with another module's write | A service call in the same session; the owning module's service arranges stage, publish and commit | `activity` bulk gear update |
| React to a fact, derive state, tolerate delay | Publish an event; the consumer subscribes; declare a reconciliation net | thumbnails and geocoding reacting to `activity.created` |
| A lower layer needs something only a higher layer knows | A seam (registry, base class, Protocol) owned by the lower layer, installed by composition | `contributor_registry`, `provider_registry` |

Do not use a contributor for a plain query, and do not use an event for something
the caller needs the answer to.

## Configuration is read by the application layers

`core.config` is the application's settings, which makes it a dependency like a provider:
it has to be visible in a signature, not discovered in a function body. A converted module
therefore reads it only in the layers that decide (`service`, `router`, `public_router`,
`dependencies`, `subscribers`, `scheduled_jobs`, `integration_service`,
`migration_service`). Every other file is a pure layer, and a value it needs is a
parameter: the file parsers take the fallback `default_timezone`, the thumbnail renderer
takes a `user_agent`, and a `BulkImportSource` that needs a directory names none and lets
the entry service apply the default. `TestConfigurationReads` fails on a `core.config`
import anywhere else, so the rule holds for a file added next year.

## What a module may take from `core`

`core.*` is "always allowed" today, and it is the largest hidden coupling between
a module and *this* application: configuration, logging, database session,
exceptions, pagination, timezone, uploads. It is not enforced yet. Treat it as a
declared dependency rather than free: prefer a primitive that is already generic
(`core.exceptions`, `core.timezone`, `core.pagination`) over adding a new reach
into application-wide state (`core.config`, `core.middleware`), and put anything
generic enough to be shared by other products into `jasil`.

For converted modules this is an allowlist:
`tests/architecture/test_converted_module_dependencies.py` names every `core`
module `activities` and `followers` may import, with the reason, and fails both
on an import that is not listed and on an entry nothing uses any more. Unconverted
modules are outside it.

## Inverting a platform-to-domain reach

When the platform appears to need something from a module, the module registers
it rather than the platform importing it. Three worked examples live in the tree:

| Reach | Inversion |
| --- | --- |
| The scheduler needed each module's recurring jobs | Each module declares `scheduled_jobs.recurring_jobs()`; `main.py` collects and hands the list to `start_scheduler`. |
| Ingestion needed to pull from Strava and Garmin | Providers call `activity_ingestion.integration_service.register_activity_provider`; the private registry names no provider. |
| Bulk import needed Strava-export semantics | `BulkImportFormat` is a registered layout (which members are activity files, the drop folder, how to build the source); `modules.strava.bulk_import_source` registers one and `StravaBulkImportSource` subclasses `BulkImportSource`. |
| Activity ingestion/profile restore needed child records | Each child returns typed contributor objects from `integration_service`; `app/module_registry.py` installs them in `activities.contributor_registry`. |
| Returning an activity needed its thumbnail's URL | `activity.service` asks `contributor_registry.resolve_thumbnail_url` for each activity it hands a client; `activity_thumbnail` registers the resolver at composition time. The stored key never leaves the server. |

The shape is always the same: the lower layer owns the *seam* (a registry, a base
class, a protocol), the higher layer owns the *implementation*, and a composition
root (`main.py`, `worker.py`) connects them. A registration performed in one
entrypoint must be performed in the other — a provider or subscriber registered
in the API but not the worker silently does nothing wherever its work is claimed.

## Sharing behavior between peer modules

When several modules perform the same operation over different rows, the
operation lives once in its owning module and peers consume its public behavior.
`activity/child_collection_service.py` is the worked example: the root activity package
owns the parent access rule and publishes `ChildCollection` through
`activity.integration_service`. Laps, sets and workout steps state their hide
flag, CRUD calls and page type without importing the private helper file.

The test for whether something belongs in such a seam is not "is this repeated?"
but "would a divergence here be a bug?". Three copies of a docstring are
harmless; three copies of an access decision are three chances to get it wrong.

`activities/contributors.py` is the second worked example:
`child_ingestion_contributor` and `child_profile_contributor` hold the parent-id
guard and the re-keying filter that laps, sets and workout steps share. Each
child supplies only its CRUD write, its archive names and how one archived record
becomes a stored row.

## Runtime behaviour

The import and layer rules say where code lives. These say how it must run, in one
process and across replicas alike. Tests do not enforce them yet, so review does.

- **No transaction across external I/O.** A service that has read rows and then calls the
  network (tile server, geocoder, provider API), renders, parses a file or writes to object
  storage ends the read transaction (`db.commit()`) first. An open transaction pins a pool
  connection and a snapshot for as long as the call takes, and the pool is shared with every
  request.
- **Claim work with one conditional `UPDATE`.** Delivery is at-least-once, so a job or batch is
  claimed with `UPDATE … WHERE status = 'pending' OR the claim is older than the lease` and the
  caller checks the row count; read-then-write is a race. A failed attempt returns the job to
  `pending` before re-raising, so the retry can claim it
  (`activity_ingestion.crud.mark_processing`, `followers.crud.accept_follower`).
- **Subscribers are cheap, idempotent and run off the request.** On the in-process bus they run
  on a small background pool (`app/module_registry.py`); on Redis, on the consumer thread. Either
  way a subscriber opens its own session, assumes it may run twice or not at all, and relies on
  its reconciliation net. Nothing may assume a subscriber finished before the response.
- **Threads inherit context.** Work handed to a pool runs under `contextvars.copy_context()`, so
  the request id reaches its logs and events.
- **Every storage area has an owner, a lifecycle and an erasure path.** The domain that writes an
  area states who deletes its blobs when the parent goes, which sweep catches what an event
  missed and, for user data, how account deletion removes it. An area missing one is incomplete.
- **Maintenance scans are bounded.** A scheduled pass pages by id with a batch constant or lists
  storage by prefix in batches; it never loads a whole table or area into memory.
- **Every outbound call has a timeout**, and a request path never waits on a lock or the pool
  longer than its client would.

## Enforcement

Two mechanisms, deliberately:

**`backend/.importlinter`** — what import-linter is good at: external packages
(`redis`, `requests`, `fastapi` in the parsers), the platform direction
(`core` never imports `modules`), the auth boundary, the migration surface and a
few named design seams. Run in CI by `.github/workflows/test-backend.yml`:

```bash
cd backend && PYTHONPATH=app uv run lint-imports
```

It matches exact module names, so it is **not** where layer rules live: a
qualified stem (`pipeline_service`) escaped a name-based contract, and a flat
module needed its own copy. Those rules are stated once, by role, as allowlists,
in `TestLayerRules` below.

**`backend/tests/architecture/test_module_boundaries.py`** — everything
import-linter cannot express, including the layer rules. A `forbidden` contract rejects an import if *any*
source matches *any* forbidden module, so "a package may import its own `crud`
but not a peer's" is not statable: the wildcard pair
`modules.activities.* → modules.activities.*.crud` also rejects
`activity_laps.service → activity_laps.crud`. The conformance test walks the AST,
compares each import against the importer's own package, and consults an explicit
allowlist containing only composition edges and exact read-model projections.

- `TestLayerRules` states each layer rule once, by file role, for every converted
  module: only persistence (`models`, `crud`, `serializers`, `query`) imports an
  ORM `models` module; a router never reaches `crud`, `models`, `query` or
  `event_publishers`; persistence imports no FastAPI and asks no other package
  (only its data shapes); a converted module reaches another top-level module
  only through its `integration_service`, `schema`, `contracts`, `constants`,
  `events` or `dependencies`; and a lower module (followers) never imports the one
  above it. They are allowlists, so a new file is covered the day it is written.
  `_LAYER_EXCEPTIONS` is the register of deliberate seams, each with its reason.
- It checks module-level files too, not just sub-package ones, which is the whole
  surface of a flat module such as `followers`.
- It resolves each `from x.y import z` against the filesystem rather than counting
  dots, so a symbol imported from a flat module is not read as a package reach.
- The allowlist is the debt register. Every entry names a real cross-package reach
  and why it exists, and may not be used for service, CRUD, model, query, signing,
  parser or storage access that belongs behind an integration surface.
- The package-level import graph inside a module is asserted to be a DAG: two
  packages that import each other are one package pretending to be two. A derived
  subsystem depends on the thing it derives from, never the reverse; when the
  depended-on package needs something back, it states a seam and composition
  installs the answer.
- `TestModuleInventory` fails on a top-level module that is neither converted nor
  explicitly outstanding.
- `test_only_transaction_owners_end_transactions` is the commit rule as an
  allowlist: only `service`, `migration_service`, `subscribers` and
  `scheduled_jobs` files may end a transaction, so a file named for no role is
  not exempt.

**`backend/tests/architecture/test_logging_rule.py`** and
**`test_route_conventions.py`** state the logging, route-declaration,
rate-limit and `db`-position rules by what the code does, over every converted
module. Where a rule needs an exception it is a register with a reason that fails
when it goes stale, not an exemption in the rule.

## Adding a module

1. Create either `modules/<name>` or a package under a composition namespace such
   as `modules/activities/<name>`; `__init__.py` contains a docstring only.
2. Add `integration_service.py`. It is the sole behavioral import path for peers
   and outside modules; keep it limited to operations with real callers. A
   package nothing else calls (`activity_geocoding`, purely reactive) has none
   and is listed with its reason in `_NO_CROSS_MODULE_SURFACE`.
3. Add `model_registry.py` when the module owns a table, and add its contribution
   to the namespace/application model registry.
4. Add `migration_service.py` only when an existing data migration needs a
   domain operation; expose that operation and no more.
5. Add `subscriber_registry.py` if the module has subscribers, and `scheduled_jobs.py`
   if it has recurring work. Register both with one `RuntimeModule(name=..., ...)`
   entry in `app/module_registry.py`. `main.py` and `worker.py` both consume that
   list, so registering "in the API but not the worker" is not possible.
6. Add startup backfills as `StartupTask`s on the same `RuntimeModule` entry.
7. For an activity child parsed or archived as JSON, add the applicable
   `ingestion_contributor`, `profile_contributor`, or
   `profile_global_contributor` factory to `integration_service.py`, then register
   that factory in `app/module_registry.py`. Do not register at import time.
8. Add the module to the source lists of the cross-module contracts in
   `backend/.importlinter`.
9. Add a new top-level bounded context to `CONVERTED_MODULES` in
   `backend/tests/_helpers/module_roles.py`; the architecture and logging tests
   both read it from there. A module that is in neither `CONVERTED_MODULES` nor
   `UNCONVERTED_MODULES` fails `TestModuleInventory`, so a module cannot be added
   outside the rules by omission.

## Conventions that look like drift

These differ between packages on purpose, or are settled so the next module follows
one pattern. Recorded here so a review does not reopen them.

**Settled (follow these in a new module):**

- **Event publishers.** `publish_<fact>(<ids>, db, *, commit, <extras>)`: `db` and
  `commit` are required and `commit` is keyword-only. A publisher with an optional
  `commit` has a best-effort path that lets a caller publish outside the
  transaction, which is what `publish_committing` exists to prevent.
- **Import aliases.** An alias is the *containing package* plus the role, so the
  name says whose file it is and which side of the visibility rule a call site is
  on. A peer's surface is `<package>_integration` (`activity_laps_integration`,
  `followers_integration`, `activity_integration` for the root `activity`
  package); a private module is `<package>_<role>` (`activity_crud`,
  `activity_laps_service`). A namespace-level file lives in `activities`, so it is
  `activities_<role>` (`activities_contributors`, `activities_computation`).
- **Capability-token routes.** The service verifies the signed token and raises
  `NotFoundError`; the router only serialises the bytes. A router never imports
  `HTTPException` or a logger.
- **ORM mapping.** `serializers.py` exposes `to_read_schema` (and `to_orm` where
  `crud` builds rows). A private `_to_*` helper inside `crud.py` is the same job in
  a second home.
- **`db` parameter.** In `service`, `crud`, `integration_service` and every other
  non-framework file, `db` is the last required positional parameter and
  keyword-only options follow it. Routers and `dependencies` are exempt: FastAPI
  resolves their parameters by name, so they order them by dependency
  (`test_db_is_the_last_required_positional_parameter`).
- **Private helper docstrings.** A `_private` function gets a summary line, and an
  `Args` section only for a parameter whose meaning is not obvious from its name and type
  (never `db: Database session.`). Public functions document every parameter.
- **Helper file names.** `<thing>_utils.py`, never `utils_<thing>.py`, so the role
  reads at the end of the stem like every other role.
- **Route defaults.** The default `200` is not repeated in `status_code`. Handler
  names are OpenAPI `operationId`s, so renaming one is an API change.
- **Route declarations.** A JSON route declares `response_model`; a route that
  returns bytes declares `responses=` (or `response_class`) with its media type.
  A write (`POST`/`PUT`/`PATCH`/`DELETE`) names its rate-limit tier; reads take
  the global default (`TestRouteConventions`).
- **Comments and docstrings.** They state what the code does now and why. History
  (what a file "used to" do, a ratio of removed duplication, a refactor's
  motivation) belongs in the commit message or PR, where it can be dated and
  corrected, not in the source, where it goes stale.
- **Logging.** A service function that refuses a caller (`PermissionDeniedError`)
  or ends a transaction logs in the same function; a service that only delegates
  has no such function and logs nothing. A file with no role logs only when it is
  listed with its reason in `_HELPERS_THAT_LOG`, and `console=True` is for
  bulk-import progress and migrations (`test_logging_rule.py`).
- **Read models.** The schema a client receives as a response body is `<Thing>Read`
  (or `<Thing>Page`); the ORM class keeps `<Thing>`. A schema and an ORM class never
  share a name, and the OpenAPI component name is the schema's. A value object nested
  inside a read model (`SummaryMetrics`, `DaySummary`) keeps its descriptive name.
- **Read models are stored rows.** A `<Thing>Read` that carries an `id` requires it: it is
  what the server returns, never what a producer sends. A read model identified by a natural
  key (`FollowRelationshipRead`: follower and followee) has no `id` and needs none. A shape that is written
  before it has an id (parsed, archived or restored data) is `<Thing>Create` in
  `contracts.py`, and both derive from a shared `<Thing>Base` in `schema.py`
  (`activity_sets`, `activity_workout_steps`, `activity_exercise_titles`). An
  optional `id` on a read model is the symptom of one class doing both jobs.
- **Status vocabularies.** A closed set a column stores (`FollowStatus`,
  `IngestionJobStatus`) is a `StrEnum` in `constants.py`, imported by `models`,
  `crud`, `service` and `schema` alike. `schema.py` only references it as a field type.
- **Page arguments.** `page_number` and `num_records` follow `db` as keyword-only
  arguments, with `core.pagination.DEFAULT_NUM_RECORDS` / `DEFAULT_CHILD_NUM_RECORDS`
  as the defaults, never a literal.
- **Access decisions are service.** A helper that decides what a caller may see and
  logs the refusal (`activity/child_collection_service.py`) is named
  `<thing>_service.py`, even when other services consume it.
- **Request parameters.** A path or query parameter's constraint is part of its type
  (`core.dependencies.PositiveId`, an enum for a closed set, `AfterValidator` for a
  vocabulary lookup), so FastAPI validates it, answers with the validation problem
  document and publishes the accepted values in OpenAPI. A `dependencies.py` does not
  raise `HTTPException`, and a child router declares the shared alias
  (`activity_dependencies.ActivityId`) on its own handlers rather than mounting a
  dependency whose only job is to carry the parameter.
- **Refusals answer 404, and say so in the log.** Reading someone's follower network or
  deleting a follow relationship you are not part of is answered as not found, the same
  as an activity the caller cannot see, so an endpoint cannot be used to probe who exists
  or who follows whom. `PermissionDeniedError` is for a caller who is entitled to know
  the resource exists but may not change it. What the server logs depends on what the
  code knows:

  | The code knows | Raises | Logs |
  | --- | --- | --- |
  | It is refusing a caller (bad capability token, a network the caller may not view) | `AccessConcealedError` (renders as the same 404) | WARNING in the same function |
  | The caller is entitled to know the resource exists | `PermissionDeniedError` | WARNING in the same function |
  | The record is missing, or a missing record cannot be told from a refusal (an empty page, `owns_activity` is false) | `NotFoundError` or an empty page | DEBUG at most |

  `test_a_service_decision_is_logged` enforces the first two rows: a service function that
  raises either refusal logs at WARNING in that same function.
- **Request bodies.** A shape a client sends is named for what it does (`<Thing>Edit`,
  `<Thing>Create`, `FollowRequestAccept`) and lives in `schema.py`; the same shape fed by
  a parser or an archive rather than a client is `<Thing>Create` in `contracts.py`. A
  `<Thing>Read` is never accepted as input (`TestReadModelsAreStoredRows`).
- **Collections.** A list a client receives is a `core.pagination.Page`; a
  collection that is absent is `[]`, never `None`. The two exceptions are the
  exercise-title reference table (`/all`, read whole by design) and the response
  to a bulk import (the handles of the jobs that POST created).
  `None` is kept only where it is a distinct signal: the ingestion store
  functions return `None` for "this file failed" and a list for "it parsed".

**Intentional variation:**

- **`migration_service`.** Pure reads and constants are re-exported by alias; every
  write is a wrapper that owns the commit the CRUD no longer performs, so a
  migration's unit of work is stated in one function.
- **Component payload shape.** The ingestion contract carries what each parser
  emits: laps as dicts, sets as raw FIT rows or `ActivitySetsCreate`, workout steps
  as schemas. Normalising them is a change to `ParsedActivity.components` and
  every parser, not to the children, so `serializers.to_orm` absorbs the
  difference at the persistence edge.
- **Job runners own their sessions.** `run_upload_job`, `run_refresh_job`,
  `run_bulk_import_job` and `fail_ingestion_job` open `SessionLocal` themselves: they are the entry point of a durable job and need
  separate transactions (mark processing, do the work, record the failure) so a
  failed unit of work cannot poison the record of the failure.
- **Provider resolution on a surface.** A surface function resolves the provider
  only when none of its callers carries one (`attach_media_bytes`, called per file
  from the Strava import). The functions whose callers already hold the provider
  (`list_media_blobs`, `store_media_blob`, the file-storage functions) take it as
  an argument.
- **Contributor helper names and `contracts.py`.** The plain child collections (laps,
  sets, workout steps) share `child_*_contributor`, so each has `_store_*`,
  `_list_*_for_activities` and `_parse_profile_record`. Streams, media and exercise
  titles persist or restore something that is not a row-per-activity list, so their
  private helpers are named for that (`_persist_ingestion_component`,
  `_restore_profile_records`). A package has a `contracts.py` only when it defines an
  input shape its `schema.py` does not (`activity_sets`, `activity_streams`,
  `activity_media`, `activity_workout_steps`, `activity_exercise_titles`); laps
  hand their contributor plain dicts, so they have none.
- **`activity_file_storage` has no `service.py`.** It is a leaf over
  `StorageProvider` with no decision to arrange, so a service would only forward.

## Known debt

Tracked here so it is visible rather than discovered. Each item is enumerated in
the conformance test's allowlist.

### Runtime rules not yet met

- **Storage lifecycle.** The `bulk_import_errors` area has no sweep, retention or account-deletion
  removal, and the thumbnail reconciliation lists its whole area each pass.
- **Timeouts.** The pool (20 + 40, 180 s wait) and the absence of a `statement_timeout` are
  constants in `core/database.py`, not settings, so an operator cannot bound them.
- **Observability.** Logs are the only signal; queue depth, job
  duration and dead-letter counts are not exported as metrics.
- **Visibility across modules.** The followee set reaches `activity.crud` as an id list, which
  grows with the follow count. A peer-published, read-only query fragment (a followee subquery)
  would avoid the list but needs its own allowed-import entry and test, so it is undecided.

### Pilot status and what the next conversion owns

`activities` and `followers` are the only modules converted so far. The
remaining modules are listed in `UNCONVERTED_MODULES` so that
`TestModuleInventory` keeps them visible rather than silently exempt, and are
converted one at a time with the `convert-module` skill. The items below need
changes outside the two converted modules, so they are recorded here as accepted
limitations rather than half-done:

- **Top-level cycles.** `users` ⇄ `activities` (profile export/import consumes
  activities; activities consumes `users.integration_service`) and, by the
  contracts' own description, `gears` ⇄ `activities`. The planned fix is the
  contributor pattern the activity children already use: `users_profile`
  export/import asks each module for its section instead of importing them.
  A `layers` contract (core, identity, followers/gears/health, activities,
  providers) then states the module-level direction once. Every edge that closes
  a cycle lives in `users` or `gears`; the activities side already publishes the
  contributor surface, so the cycles stay until those modules are changed.
- **Layer rules for unconverted modules.** `TestLayerRules` covers converted
  modules only. An unconverted module is outside it until converted, and the
  `auth-boundary` contract is the one generic rule over every module:
  `TestAuthBoundaryCoverage` fails when its source list differs from the set of
  top-level modules, so a new module cannot start unconstrained.
- **Registration seams.** `RuntimeModule` in `app/module_registry.py` is the
  per-module manifest for subscribers, durable handlers, nets, recurring jobs and
  startup tasks. Routers (`api.py`) and models (`model_registry.py`) stay
  separate composition surfaces on purpose: they have different consumers
  (the HTTP app and Alembic), and the legacy model scan keeps the model seam
  distinct until the unconverted modules are gone.
- **Namespace-level code in `health`.** `health` has `router.py`, `schema.py`
  and `utils.py` beside its sub-packages, which conflicts with "a composition
  namespace is not an implementation boundary".
- **`auth` naming.** `identity_service.py` and `_internal/` instead of
  `integration_service.py` and the filename vocabulary, as described above.
  The generic boundary rule needs a special case until it is aligned.

- **Persistence layers calling other modules.** Converted modules ask nothing of
  another bounded context below `service` (`TestLayerRules`). The unconverted ones still do,
  for example `health.*.crud` reaching `users.users.utils` and
  `notifications.utils` reaching `users` and `websocket`.
- **Persistence ending transactions.** Converted modules stage with `flush()` and
  let `service` (or the job, importer or `migration_service` that owns the unit of
  work) commit. Unconverted modules (`auth`, `users`, `gears`, …) are outside
  `test_crud_does_not_end_transactions`; `_CRUD_TRANSACTION_DEBT` is empty and is
  where a module being converted lists its files.
- **Subscribers reaching past a surface.** Followers holds no subscribers; its
  notification handlers live in `modules/notifications` and subscribe to
  `followers.events` (`TestLayerRules`). `garmin`, `strava`,
  `auth.sign_up_tokens` and `users.users_profile` still import another module's
  `utils`/`manager` directly.
- **Legacy model scan.** Converted modules declare their ORM module in
  `model_registry.py` and use scalar foreign keys with database `ON DELETE`
  behaviour. `app/model_registry.py` keeps a filesystem scan only for modules not
  converted yet.
