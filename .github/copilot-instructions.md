# Endurain Fitness Tracking Application

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

---

## AI / Copilot Behavior Guidelines

- Always follow instructions in this file before inferring new patterns.
- Do **not** suggest changes to Dockerfiles or CI/CD workflows unless they clearly violate instructions here.
- For Vue components:
  - Use `<script setup lang="ts">` syntax.
  - Follow the 10-section component structure.
  - Prefer utilities from `/utils` and constants from `/constants`.
- Do not alter port numbers, environment variables, or framework versions unless explicitly instructed.
- Prefer using existing validation, constants, and type files rather than creating new ones.
- Use the timing benchmarks in this document to evaluate build success or performance anomalies.
- **Documentation files:** When creating new development documentation files (e.g., `BACKEND_AUTH_DEVELOPMENT_LOG.md`, `OBSERVABILITY_STRATEGY.md`), store them in the `devdocs/` folder. This folder is gitignored and used for local development documentation that should not be committed to the repository.
- **Development/helper scripts:** When creating new development/helper scripts, store them in the `devscripts/` folder. This folder is gitignored and used for local development scripts that should not be committed to the repository.
- **Do ONLY what is explicitly requested** - do not add extra documentation, summaries, or "helpful" files unless specifically asked.
- If asked to implement a feature, implement ONLY that feature - no additional documentation beyond code comments.
- Do not create README files, summary documents, quick reference guides, or completion reports unless explicitly requested.
- When implementing changes, focus on the code implementation itself, not supplementary documentation.
- Ask for clarification if the scope is unclear rather than assuming additional deliverables are wanted.

---

## Working Effectively

Endurain is a self-hosted fitness tracking application built with Vue.js frontend, Python FastAPI backend, and PostgreSQL database. The primary development workflow uses Docker, but frontend-only development is supported for faster UI iteration.

### Prerequisites and Environment Setup

- **Node.js:** v20.19.4 (for frontend)
- **Python:** v3.13 (backend)
- **Docker:** required for full-stack development and CI/CD builds
- **Poetry:** for backend dependency management (when not using Docker)

### Quick Start Development Setup

1. Clone repository: `git clone https://github.com/joaovitoriasilva/endurain.git`
2. Navigate to the project root
3. Choose development approach:
   - **Frontend Only** – see _Frontend Development_
   - **Full Stack** – use _Docker Development Setup_

### Frontend Development (Recommended for UI changes)

- Navigate: `cd frontend/app`
- Install dependencies: `npm install` (≈20 seconds)
- Start dev server: `npm run dev` (port 5173 or 5174 if occupied)
- Build frontend: `npm run build` (≈9 seconds)
- Format code: `npm run format` (≈5 seconds)
- **Note:** ESLint configuration pending migration to flat config format (lint fails currently)
- **Note:** Unit tests not yet implemented (`npm run test:unit` exits with “No test files found”)

### Docker Development (Full Stack)

- Build unified image: `docker build -f docker/Dockerfile -t unified-image .`
- **Caution:** Docker builds may take 15–20 minutes. Avoid canceling unless hung for 30+ minutes.
- **CI Caveat:** SSL certificate errors can occur during CI builds; document but don’t bypass validation.
- Create docker-compose.yml from the provided example.
- Start services: `docker compose up -d`
- Stop services: `docker compose down`

### Backend Development (Advanced)

- Python 3.13 backend managed by Poetry
- Codebase in `backend/` with `pyproject.toml`
- Use Docker if system Python < 3.13
- Install Poetry: `pip install poetry`
- Install dependencies: `poetry install`

#### Backend Code Quality Standards

- **Modern Python Syntax (Python 3.13):**
  - Use union types with `|` operator: `str | None` instead of `Optional[str]`
  - Use built-in generics: `list[str]` instead of `List[str]`, `dict[str, int]` instead of `Dict[str, int]`
  - No imports from `typing` module for `Optional`, `List`, `Dict`, `Tuple`, `Set` – use native syntax
  - Example: `def get_user(user_id: int) -> User | None:`
  - Example: `async def get_activities(limit: int = 10) -> list[Activity]:`
- Use type hints (`def foo(x: int) -> str:`)
- Standard FastAPI project layout: `routers/`, `schemas/`, `services/`, `models/`
- Public functions/classes must have docstrings
- Core logic should live in `services/`, not routers
- Format with `black` and `isort`
- Include at least one unit test per router or service

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

### Pre-commit Validation

- Run `npm run format` before commits
- Confirm successful `npm run build`
- Ensure `npm run dev` runs without warnings/errors

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

## Code Quality Standards (10/10 Quality)

### Frontend Component Standards

#### TypeScript

- Always use `<script setup lang="ts">`
- **Modern Type Inference:**
  - Use `ref<T>()` with generic parameter: `const user = ref<User | null>(null)`
  - **Avoid** redundant `Ref<T>` annotations: ~~`const user: Ref<User | null> = ref(null)`~~
  - Let TypeScript infer types when obvious: `const count = ref(0)` (infers `Ref<number>`)
  - Let `computed()` infer return types from callback
  - **Avoid** redundant `ComputedRef<T>` annotations
- Explicit typing for function parameters and return types
- Type imports for complex types: `Router`, `RouteLocationNormalizedLoaded`
- No implicit `any` types
- Centralized imports from `/types/index.ts`

#### Documentation

- Each component must include a clear, purposeful JSDoc overview
- Document complex logic; skip redundant auto-generated comments

#### Component Structure (10 Sections)

1. Fileoverview JSDoc
2. Imports
3. Composables & Stores
4. Reactive State
5. Computed Properties
6. UI Interaction Handlers
7. Validation Logic
8. Main Logic
9. Lifecycle Hooks
10. Component Definition

#### Centralized Architecture

- **Validation utilities:** `/utils/validationUtils.ts`
  - `isValidPassword()`, `passwordsMatch()`, `isValidEmail()`, `sanitizeInput()`
  - Password strength analysis functions
- **Constants:** `/constants/httpConstants.ts`
  - `HTTP_STATUS` enum for status codes
  - `extractStatusCode()` for error response parsing
  - `QUERY_PARAM_TRUE` for URL parameters
- **Type definitions:** `/types/index.ts`
  - `ErrorWithResponse`, `NotificationType`, `ActionButtonType`
- **Bootstrap modals:** `/composables/useBootstrapModal.ts`
  - Modal lifecycle management

#### UI/UX Standards

- Use Bootstrap 5 `form-floating` classes
- Accessibility:
  - All interactive elements must have `aria-label`
  - Use `aria-live="polite"` for validation messages
  - Ensure full keyboard navigation
- Responsive across mobile, tablet, desktop
- Always include loading states and graceful error handling

#### Accessibility Testing Checklist

- Verify tab navigation for all forms
- Check color contrast meets WCAG AA
- Validate `aria-label` coverage
- Confirm focus outlines visible and consistent
- Test screen reader compatibility (NVDA/VoiceOver)

#### Reference Implementations (10/10 Quality)

Study these files as templates when creating/refactoring components:

- **LoginView.vue** (437 lines) - Authentication with MFA support
- **SignUpView.vue** (611 lines) - Registration with optional fields
- **ResetPasswordView.vue** (~320 lines) - Password reset with token validation
- **ModalComponentEmailInput.vue** - RFC 5322 email validation

### Backend Component Standards - Python Code Style Requirements

#### Modern Python Syntax (Python 3.13+)
- Use modern type hint syntax: `int | None`, `list[str]`, 
  `dict[str, Any]`
- Do NOT use `typing.Optional`, `typing.List`, `typing.Dict`, etc.
- Target Python 3.13+ features and syntax

#### PEP 8 Line Limits
- Code lines: **79 characters maximum**
- Comments and docstrings: **72 characters maximum**
- Enforce strictly - no exceptions

#### Docstring Standard (PEP 257)
- **Always follow PEP 257** with Args/Returns/Raises sections
- **Format**: One-line summary, blank line, then 
  Args/Returns/Raises sections
- **Always include Args/Returns/Raises** even when parameters seem 
  obvious
- **NO examples** in docstrings - keep in external docs or tests
- **NO extended explanations** - one-line summary + sections only
- **Keep concise** - describe what, not how

**Function docstring format:**
```python
def function(param: str) -> int:
    """
    One-line summary of what this does.

    Args:
        param: Description of param.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param is invalid.
    """
```

**Class docstring format:**
```python
class MyClass:
    """
    One-line summary of the class.

    Attributes:
        attr: Description of attribute.
    """
```

---

## Code Review Checklist

- ✅ TypeScript with explicit types
- ✅ Meaningful JSDoc documentation
- ✅ 10-section component structure
- ✅ Centralized use of validation/constants/types
- ✅ Bootstrap 5 form-floating usage
- ✅ Accessibility attributes verified
- ✅ Code formatted successfully (`npm run format`)
- ✅ Build passes (`npm run build`)
- ✅ Manual browser validation complete
- ✅ No console warnings/errors

---

## Development Workflow

1. Edit code in `frontend/app/src/`
2. Run `npm run dev` to test locally
3. Run `npm run format` before commit
4. Build production output with `npm run build`
5. For backend changes, use Docker setup
6. Validate full UI flow manually

---

## Architecture Notes

- **Frontend:** Vue.js 3, Vite, Bootstrap 5, Chart.js, Leaflet
- **Backend:** FastAPI, SQLAlchemy, Alembic
- **Database:** PostgreSQL
- **Integrations:** Strava, Garmin Connect
- **File Imports:** .gpx, .tcx, .fit
- **Auth:** JWT with 15-minute access tokens
- **Deployment:** Docker multi-stage builds, multi-architecture images

---