# Endurain

Self-hosted fitness tracking application.
Backend: Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, and the `jasil` platform package.
Frontend: Vue 3, TypeScript, Vite, Tailwind CSS v4, shadcn-vue, TanStack Query, Pinia.
Deployment: Docker multi-stage image (amd64, arm64).

## Where the detail lives

| Working on | Read |
| --- | --- |
| Backend code or tests | `.agents/skills/endurain-backend/SKILL.md` |
| Frontend code or tests | `.agents/skills/endurain-frontend/SKILL.md` |
| Converting a module to the module structure | `.agents/skills/convert-module/SKILL.md` |
| Commit messages and PRs | `.agents/skills/conventional-commits/SKILL.md` |
| Writing or editing a skill | `.agents/skills/skill-authoring/SKILL.md` |
| Module rules and file roles | `docs/developer-guide/module-structure.md` |
| Identity and auth boundary | `docs/developer-guide/auth-boundary.md` |
| Visual design | `docs/developer-guide/brand-and-ux-guidelines.md` |
| Scaling, jobs, storage settings | `docs/getting-started/scaling-and-background-jobs.md` |

Skills are plain Markdown; read the relevant `SKILL.md` and the reference files it points to when your tool does not load skills itself.

## Layout

```text
backend/        FastAPI app (app/), tests (tests/), pyproject.toml, .importlinter
frontend/       Vue app (src/), package.json
docs/           Documentation site (mkdocs)
docker/         Dockerfile and start.sh
.agents/skills/ Agent skills (symlinked into .claude/skills)
```

## Commands

Backend (from `backend/`, Python 3.13, `uv`):

```bash
uv sync
PYTHONPATH=app uv run lint-imports
uv run pytest tests/<area> -q
uv run ruff format --check . && uv run ruff check .
```

Frontend (from `frontend/`, Node 24):

```bash
npm install
npm run dev
npm run check        # type-check + lint + format + tests (CI gate)
npm run gen:api      # after backend API changes
```

## Rules for every change

- Do only what was asked; no extra docs, summaries, READMEs or "helpful" files.
- Prefer existing patterns, utilities and files over new ones.
- KISS: pick the simplest design that works; no indirection, abstraction layer or option without a current need.
- YAGNI: build only what the task needs now; no speculative parameters, flags, hooks, config or extension points.
- DRY: reuse an existing helper, schema, composable or primitive before writing another; extract shared code at the third repetition, not the second, and only when the copies change for the same reason.
- Do not change Dockerfiles, CI workflows, port numbers, environment variables or framework versions unless asked.
- Never run `git commit` (or any commit-creating command) unless the user explicitly asks; staging for inspection is fine.
- Commit messages and PR titles follow Conventional Commits (enforced in CI); see the `conventional-commits` skill.
- Local-only notes go in `devdocs/`, helper scripts in `devscripts/` (both gitignored).
- All `UploadFile` handling goes through `backend/app/core/file_uploads.py`; never build filesystem paths from user filenames.
- No hardcoded secrets; read configuration from environment variables.
- Ask for clarification when scope is unclear instead of assuming extra deliverables.

## Backend invariants

- Module boundaries, layering, transactions and identity follow `docs/developer-guide/module-structure.md` and `docs/developer-guide/auth-boundary.md`; they are not restated here.
- `crud` raises `core.exceptions`, not `HTTPException`; `service` owns transactions and publishes events.
- Storage, events, jobs and geocoding come from `jasil` ports; resolve a provider at the entry point and pass it down.
- Comments state what the code does now, not what it used to do.
- Enforced by `backend/.importlinter` and `backend/tests/architecture/`.
- Python 3.13 syntax, 120-character lines, Google-style PEP 257 docstrings (`Args`, `Returns`, `Raises` where applicable; ruff `D` enforces them on converted modules).

## Frontend invariants

- Code lives in `src/features/<feature>/`; server state through TanStack Query, client state in Pinia, HTTP through `src/services/http.ts`.
- Types come from the generated API client (`src/types/api.generated.ts`, never hand-edited).
- Semantic Tailwind tokens and shadcn-vue primitives; no hardcoded hex values; every string through vue-i18n.
- Never use `v-html` on user data.
