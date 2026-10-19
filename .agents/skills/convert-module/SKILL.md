---
name: convert-module
description: Convert a legacy backend module to the module structure. Use when refactoring a module under backend/app/modules to follow docs/developer-guide/module-structure.md.
---

# Convert a module to the module structure

Rules and file roles: `docs/developer-guide/module-structure.md` and the `endurain-backend` skill.
`activities` and `followers` are the converted reference modules; copy their shape, not their activity-specific contracts.

## Before you start

1. Read the module's current files and list every import it makes from, and receives from, other modules.
2. Check Known debt in the guide for what is already recorded for this module.
3. Convert one top-level module per commit series; do not mix in behaviour changes.
   - Keep it minimal (KISS, YAGNI): move and rename existing code; do not add layers, helpers or surface operations nobody uses.
4. Run the gates once on the untouched module to know the baseline.

## Procedure

1. **Classify files by role** using `tests/_helpers/module_roles.py` (`models`, `crud`, `service`, `router`, `schema`, ...).
   - Rename any file whose name hides its role (`foo_utils.py` that queries the DB becomes `crud.py`).
   - Make `__init__.py` a docstring only; fix imports that relied on re-exports.
2. **Split persistence from decisions.**
   - Only `crud.py` (or `<thing>_crud.py`) runs statements and returns schemas/DTOs, never ORM rows.
   - Move access checks, orchestration, event publishing and commits into `service.py`.
   - `crud` never calls another module: resolve what it needs in `service` and pass it in.
3. **Make routers thin.** Validate, delegate to `service`, return; no `crud`, `models` or `event_publishers` imports.
4. **Errors.** `crud` and `service` raise `core.exceptions`, not `HTTPException`.
5. **Publish a surface.** Create `integration_service.py` with only operations that have an outside caller.
   - Callers in other modules switch to it; they stop importing `service`, `crud`, `models`, `utils`.
   - A surface function that only forwards goes straight to `crud` instead of through `service`.
   - It must not publish events or own a commit.
6. **Contracts.** Put inter-module DTOs in `contracts.py`; keep `schema.py` for client shapes.
7. **Events.** Channels and `VersionedPayload` models in `events.py`; publish from `event_publishers.py` via `service`; subscribers in `subscribers.py` with `subscriber_registry.py` and a reconciliation net (see `references/platform-jasil.md` in `endurain-backend`).
8. **Providers.** Resolve storage/geocoding/lock/state only at routers (`Depends`), subscribers, jobs or `integration_service`; pass them down.
9. **Wiring.**
   - Models: `model_registry.py`, composed in `app/model_registry.py`.
   - Runtime: one `RuntimeModule(name=..., ...)` in `app/module_registry.py` (subscribers, jobs, startup tasks).
   - Data migrations that touch the module: `migration_service.py` adapters.
10. **Break cycles.** If two top-level modules import each other, invert one edge with a registry/contributor seam owned by the lower layer and installed in `module_registry`.
11. **Enforcement.**
    - Add the module's name to `CONVERTED_MODULES` (and remove it from `UNCONVERTED_MODULES`) in `tests/_helpers/module_roles.py`.
    - Add it to the source lists of the cross-module contracts in `backend/.importlinter`; add a flat-module contract set if it has no sub-packages.
    - Add allowlist entries only for exact composition or read-model edges, each with a reason.
    - Remove the module from the ruff `D` per-file-ignores in `backend/pyproject.toml` and fix what the docstring lint finds; `TestDocstringScope` fails until it matches `UNCONVERTED_MODULES`.
    - The layer rules (`TestLayerRules`) apply to it automatically once it is in `CONVERTED_MODULES`; list a deliberate exception in `_LAYER_EXCEPTIONS` with its reason, and a surface operation that must commit in `_SURFACE_UNITS_OF_WORK`.
12. **Docs.** Update Known debt in `module-structure.md`; add a row if the module revealed a new rule.

## Gates

```bash
cd backend
PYTHONPATH=app uv run lint-imports
uv run pytest tests/architecture -q --no-cov
uv run pytest tests/<module> -q --no-cov
uv run ruff format --check . && uv run ruff check .
```

Run the full suite before opening the PR.

## Pitfalls seen in the pilot

- A misnamed file is silently exempt from every rule; `ingestion_jobs_crud.py` and `summary_query.py` both executed SQL unnoticed.
- Two packages that each use the other's public surface still form a cycle; the DAG test catches it, the import contracts do not.
- A persistence layer that "just checks one setting" in another module is a service decision in disguise.
- Putting `commit` in `integration_service` creates two write-orchestration layers; call your own `service`.
- Registration at import time works in the API and silently does nothing in the worker.
- Re-export facades in `__init__.py` hand out ORM models under a package path.
- Tests that patch `platform_runtime` hide a service-locator dependency; pass the provider instead.

## Module-specific hints

| Module | Watch for |
| --- | --- |
| `users` | Six sub-packages; `users_profile` export/import reaches `activities` and `gears`. Use the profile-contributor pattern the activity children already have. |
| `gears` | `gears` and `activities` use each other (aggregations, dependencies); invert via a contract on the lower layer. |
| `health` | Namespace-level `router.py`, `schema.py`, `utils.py` beside seven sub-packages; move them into a package or keep them composition-only. |
| `strava`, `garmin` | Providers register with ingestion through `register_activity_provider`; keep them leaf modules. `garmin.mfa_code_store` still calls `get_state()`. |
| `auth` | Surface is `identity_service.py` and `_internal/`; align naming only after the generic boundary rule exists. |
| `notifications`, `websocket` | Consumed through `integration_service`; `websocket` ticket store and auth stores use `get_state()` and need a provider argument. |
| `server_settings` | Read by many modules; expose a narrow `integration_service` and keep schema reads as data surfaces. |
