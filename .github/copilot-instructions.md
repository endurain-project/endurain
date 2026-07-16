# Endurain Fitness Tracking Application

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

**Note:** Specialized coding standards and guidelines are in separate instruction files:
- **Python/Backend:** `.github/instructions/python.instructions.md`
- **TypeScript/JavaScript/Vue/Frontend:** `.github/instructions/javascript.instructions.md`
- **Security (all files):** `.github/instructions/security-and-owasp.instructions.md`
- **GitHub Actions / CI-CD:** `.github/instructions/github-actions-ci-cd-best-practices.instructions.md`
- **Copilot Agents:** `.github/instructions/agents.instructions.md`
- **Instruction files:** `.github/instructions/instructions.instructions.md`
- **Prompt files:** `.github/instructions/prompt.instructions.md`

---

## AI / Copilot Behavior Guidelines

- Always follow instructions in this file before inferring new patterns.
- Do **not** suggest changes to Dockerfiles or CI/CD workflows unless they clearly violate instructions here.
- Do not alter port numbers, environment variables, or framework versions unless explicitly instructed.
- Prefer using existing patterns, utilities, and files rather than creating new ones.
- Use the timing benchmarks in this document to evaluate build success or performance anomalies.
- **File uploads:** All `UploadFile` handling MUST go through `backend/app/core/file_uploads.py`. Use `save_validated_upload(file, kind=UploadKind.X, upload_dir=..., filename=...)` for any new endpoint that persists an upload, and `validate_upload(file, kind=...)` when the file is consumed in memory only. Do **not** instantiate `safeuploads.FileValidator` outside that module, do **not** join user-supplied filenames into filesystem paths, and use server-generated filenames (UUID/hash/fixed name) for the destination.
- **Documentation files:** When creating new development documentation files (e.g., `BACKEND_AUTH_DEVELOPMENT_LOG.md`, `OBSERVABILITY_STRATEGY.md`), store them in the `devdocs/` folder. This folder is gitignored and used for local development documentation that should not be committed to the repository.
- **Development/helper scripts:** When creating new development/helper scripts, store them in the `devscripts/` folder. This folder is gitignored and used for local development scripts that should not be committed to the repository.
- **Do ONLY what is explicitly requested** - do not add extra documentation, summaries, or "helpful" files unless specifically asked.
- If asked to implement a feature, implement ONLY that feature - no additional documentation beyond code comments.
- Do not create README files, summary documents, quick reference guides, or completion reports unless explicitly requested.
- When implementing changes, focus on the code implementation itself, not supplementary documentation.
- Ask for clarification if the scope is unclear rather than assuming additional deliverables are wanted.
- **Do NOT run `git commit` (or any other commit-creating command) unless the user explicitly asks for it.** Stage changes if needed for inspection (`git add`), but leave the actual commit to the user. This applies even when finishing a multi-step task, when tests pass, or when changes feel "done" — wait for explicit instruction.
- **Auth boundary rule:** Non-auth modules must consume identity **only** through the public surface — `auth.dependencies` and `auth.identity_service.IdentityService`. The single `auth-boundary` contract in `backend/.importlinter` forbids non-auth code from importing the private `auth._internal` package (credential/token/lockout plumbing — `internal_dependencies`, `password_hasher`, `token_manager`, `security_stores` — and the `auth._internal.services` workflow layer) or any auth CRUD module (matched structurally by `auth.*.crud` / `auth.*.*.crud`). The boundary is fully structural: no per-module `ignore_imports` exceptions.

---

## Project Overview

Endurain is a self-hosted fitness tracking application with:
- **Frontend:** Vue.js 3 + TypeScript + Vite + Tailwind CSS v4 + shadcn-vue
- **Backend:** Python 3.13 + FastAPI + SQLAlchemy + Alembic
- **Database:** PostgreSQL
- **Integrations:** Strava, Garmin Connect
- **File Import Support:** .gpx, .tcx, .fit, .gz
- **Authentication:** JWT with 15-minute access tokens, 7 days refresh tokens
- **Deployment:** Docker multi-stage builds, multi-architecture images (amd64, arm64)

---

## Development Workflows

### Commits logic

Committing should use clear messages following [Conventional Commits](https://www.conventionalcommits.org/) format:

**Format:** `<type>(<scope>)!: <description>` — `(<scope>)` and the breaking-change `!` are optional.

The following rules are enforced automatically on every PR (against the PR title and every commit subject) by `.forgejo/workflows/conventional-commits.yml`. Validation follows the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) spec, with a single project-policy addition (the allowed-type whitelist). Generated commit messages must comply:

- **Header format:** `<type>(<scope>)!: <description>` — the `(<scope>)` and breaking-change `!` are optional, and a space is required after the colon.
- **Allowed types (project policy):** `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`. Types are matched case-insensitively per the spec.
- **Scope** (optional) is any non-empty string (no parentheses), per the spec.
- **Description** is free-form text, per the spec (no lowercase requirement, no trailing-period restriction, no length limit).
- **Breaking changes** are marked with `!` after the type/scope (e.g. `feat(api)!: ...`) or a `BREAKING CHANGE:` footer in the commit body.

Examples:
- `feat: add GPX max speed parsing`
- `fix(garmin): handle multi-segment GPX distance correctly`
- `docs: update development instructions`
- `test(activities): add regression test for GPX segment handling`
- `refactor(api)!: rename Activity.distance to total_distance`

### Prerequisites
- **Node.js:** v24 (for frontend development)
- **Python:** v3.13 (for backend development)
- **Docker:** Required for full-stack development and CI/CD builds
- **uv:** For backend dependency management (when not using Docker)

### Quick Start

1. Clone repository: `git clone https://codeberg.org/endurain-project/endurain.git`
2. Navigate to the project root
3. Choose development approach:
   - **Frontend Only** – see _Frontend Development_ below
   - **Full Stack** – use _Docker Development Setup_ below

### Frontend Development (Recommended for UI changes)

Fast iteration workflow for frontend-only development:

- Navigate: `cd frontend`
- Install dependencies: `npm install` (≈20 seconds)
- Start dev server: `npm run dev` (port 5173 or 5174 if occupied)
- Build frontend: `npm run build` (≈9 seconds)
- Format code: `npm run format` (≈5 seconds)

**Notes:**
- ESLint uses flat config (`eslint.config.ts`) with Vue + TypeScript support
- Unit tests not yet implemented (`npm run test:unit` exits with "No test files found")

**Pre-commit validation:**
- Run `npm run format` and `npm run lint` before commits
- Confirm successful `npm run build`
- CI checks: `npm run format:check`, `npm run lint:check`, `npm run type-check`

### Docker Development (Full Stack)

Complete environment for frontend + backend + database:

- Build unified image: `docker build -f docker/Dockerfile -t unified-image .`
- **Caution:** Docker builds may take 15–20 minutes. Avoid canceling unless hung for 30+ minutes.
- **CI Caveat:** SSL certificate errors can occur during CI builds; document but don't bypass validation.
- Create `docker-compose.yml` from the provided example
- Start services: `docker compose up -d`
- Stop services: `docker compose down`

### Backend Development (Advanced)

Python development without Docker (requires Python 3.13):

- Navigate: `cd backend`
- Install uv: `pip install uv`
- Install dependencies: `uv sync`
- Backend codebase in `backend/app/` with `pyproject.toml`
- **Linting/Formatting:** Uses `ruff` (configured in `pyproject.toml`)
  - Format: `ruff format .`
  - Lint: `ruff check .` (auto-fix: `ruff check --fix .`)
  - CI checks: `ruff format --check .` and `ruff check .`
- **Use Docker if system Python < 3.13**

---

## Validation

### Manual Testing Validation

- Visit login page at `http://localhost:5173/login` or `:5174`
- Verify: logo, username/password fields, “Sign in” button
- Footer must display version and integration badges
- Screenshot validation: clean, modern UI with blue sign-in button and Strava/Garmin compatibility

### Docker Validation

- Document SSL issues but complete functional validation
- Ensure built container runs successfully (even if CI SSL fails)

---

## Common Tasks

### File Locations and Structure

```plaintext
Repository root:
├── frontend/          # Vue.js frontend application
│   ├── package.json       # Frontend dependencies and scripts
│   ├── src/               # Vue.js source code
│   ├── dist/              # Built frontend output
│   └── vite.config.js     # Vite configuration
├── backend/               # Python FastAPI backend
│   ├── pyproject.toml     # Poetry dependencies
│   └── app/               # FastAPI application source
├── docker/
│   ├── Dockerfile         # Multi-stage build definition
│   └── start.sh           # Entrypoint script
├── docs/                  # Documentation
├── .github/workflows/     # CI/CD pipelines
├── docker-compose.yml.example
└── .env.example
```

### Key Commands and Timing

| Command          | Description             | Typical Duration |
| ---------------- | ----------------------- | ---------------- |
| `npm install`    | Installs frontend deps  | 5–21 s           |
| `npm run build`  | Builds frontend         | 9 s              |
| `npm run format` | Formats code            | 2–6 s            |
| `npm run dev`    | Starts dev server       | \~1 s            |
| `docker build`   | Builds full stack image | 15–20 min        |

---

## Known Issues

- Docker builds may fail with SSL issues in CI
- Backend Python 3.13 required
- No frontend test coverage yet

---

## CI/CD Workflows

- Located in `.github/workflows/`
- Common workflows:
  - `frontend.yml`: builds and lints frontend
  - `docker-build.yml`: builds multi-arch Docker images (amd64, arm64)
  - `release.yml`: publishes Docker images to GitHub Container Registry
- Use workflow dispatch for manual triggers

---