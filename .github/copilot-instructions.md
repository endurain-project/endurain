# Endurain Fitness Tracking Application

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

**Note:** Language-specific coding standards are in separate instruction files:
- **Python/Backend:** `.github/instructions/python.instructions.md`
- **TypeScript/JavaScript/Vue/Frontend:** `.github/instructions/javatsscript.instructions.md`

---

## AI / Copilot Behavior Guidelines

- Always follow instructions in this file before inferring new patterns.
- Do **not** suggest changes to Dockerfiles or CI/CD workflows unless they clearly violate instructions here.
- Do not alter port numbers, environment variables, or framework versions unless explicitly instructed.
- Prefer using existing patterns, utilities, and files rather than creating new ones.
- Use the timing benchmarks in this document to evaluate build success or performance anomalies.
- **Documentation files:** When creating new development documentation files (e.g., `BACKEND_AUTH_DEVELOPMENT_LOG.md`, `OBSERVABILITY_STRATEGY.md`), store them in the `devdocs/` folder. This folder is gitignored and used for local development documentation that should not be committed to the repository.
- **Development/helper scripts:** When creating new development/helper scripts, store them in the `devscripts/` folder. This folder is gitignored and used for local development scripts that should not be committed to the repository.
- **Do ONLY what is explicitly requested** - do not add extra documentation, summaries, or "helpful" files unless specifically asked.
- If asked to implement a feature, implement ONLY that feature - no additional documentation beyond code comments.
- Do not create README files, summary documents, quick reference guides, or completion reports unless explicitly requested.
- When implementing changes, focus on the code implementation itself, not supplementary documentation.
- Ask for clarification if the scope is unclear rather than assuming additional deliverables are wanted.

---

## Project Overview

Endurain is a self-hosted fitness tracking application with:
- **Frontend:** Vue.js 3 + TypeScript + Vite + Bootstrap 5
- **Backend:** Python 3.13 + FastAPI + SQLAlchemy + Alembic
- **Database:** PostgreSQL
- **Integrations:** Strava, Garmin Connect
- **File Import Support:** .gpx, .tcx, .fit, .gz
- **Authentication:** JWT with 15-minute access tokens, 7 days refresh tokens
- **Deployment:** Docker multi-stage builds, multi-architecture images (amd64, arm64)

---

## Development Workflows

### Prerequisites
- **Node.js:** v20.19.4 (for frontend development)
- **Python:** v3.13 (for backend development)
- **Docker:** Required for full-stack development and CI/CD builds
- **Poetry:** For backend dependency management (when not using Docker)

### Quick Start

1. Clone repository: `git clone https://github.com/endurain-project/endurain.git`
2. Navigate to the project root
3. Choose development approach:
   - **Frontend Only** – see _Frontend Development_ below
   - **Full Stack** – use _Docker Development Setup_ below

### Frontend Development (Recommended for UI changes)

Fast iteration workflow for frontend-only development:

- Navigate: `cd frontend/app`
- Install dependencies: `npm install` (≈20 seconds)
- Start dev server: `npm run dev` (port 5173 or 5174 if occupied)
- Build frontend: `npm run build` (≈9 seconds)
- Format code: `npm run format` (≈5 seconds)

**Notes:**
- ESLint configuration pending migration to flat config format (lint fails currently)
- Unit tests not yet implemented (`npm run test:unit` exits with "No test files found")

**Pre-commit validation:**
- Run `npm run format` before commits
- Confirm successful `npm run build`
- Ensure `npm run dev` runs without warnings/errors

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
- Install Poetry: `pip install poetry`
- Install dependencies: `poetry install`
- Backend codebase in `backend/app/` with `pyproject.toml`
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
├── frontend/app/          # Vue.js frontend application
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

- ESLint migration to flat config pending
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