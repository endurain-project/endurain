---
name: endurain-backend
description: Endurain backend conventions (FastAPI, SQLAlchemy 2, module structure). Use when adding, moving, refactoring or reviewing code in backend/app or backend/tests.
---

# Endurain backend

The module guide `docs/developer-guide/module-structure.md` is authoritative.
For identity use `docs/developer-guide/auth-boundary.md`.
Where this skill and a guide disagree, the guide wins.

## Core rules (always apply)

What peers may import, the layering, and who owns the transaction are stated once, in the guide
(Visibility, Layering inside a module, Transaction ownership). They are not copied here, so they
cannot drift. What an agent most often gets wrong:

- A file's name is its role; a misnamed file silently escapes the rules, so name it for what it does.
- `__init__.py` is a docstring and nothing else; never register contributors, subscribers or providers as an import side effect.
- If a rule blocks you, add the operation to the owner's `integration_service`; do not widen an allowlist.
- Resolve providers (`get_active_platform()`) only at entry points; below that, take the provider as an argument.
- Never import `jasil.backends` or `jasil._core`; identity comes only from `modules.auth.dependencies` and `modules.auth.identity_service`.
- KISS, YAGNI, DRY: search the module and `core` for an existing helper first; add no parameter, wrapper, base class or `integration_service` operation without a current caller; extract on the third repetition.
- Comments and docstrings say what the code does now and why; history goes in the commit message.

## Read on demand

| When you are | Read |
| --- | --- |
| Creating a module, deciding where code goes, wiring contributors | `references/modules.md` |
| Storage, events, subscribers, durable jobs, reconciliation nets, scheduled work | `references/platform-jasil.md` |
| Writing models, schemas, endpoints, docstrings, logging | `references/code-standards.md` |
| Raising errors, endpoints, pagination, rate limits, API changes | `references/errors-and-api.md` |
| Handling uploads, access control, secrets, outbound requests | `references/security.md` |
| Writing or fixing tests | `references/testing.md` |

## Before finishing a structural change

```bash
cd backend
PYTHONPATH=app uv run lint-imports
uv run pytest tests/architecture -q --no-cov
uv run ruff format --check . && uv run ruff check .
```

## Repo hygiene

- Do only what was asked: no extra docs, summaries or READMEs.
- Prefer existing patterns and utilities over new files; keep it simple, build only what is needed now, do not repeat existing code.
- Do not touch Dockerfiles, CI, ports, env vars or framework versions unless asked.
- Local notes go in `devdocs/`, helper scripts in `devscripts/` (gitignored).
- Never run `git commit` unless asked; use the `conventional-commits` skill for messages.
