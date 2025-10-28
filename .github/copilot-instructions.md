# Endurain Fitness Tracking Application

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

Endurain is a self-hosted fitness tracking application built with Vue.js frontend, Python FastAPI backend, and supports PostgreSQL/MariaDB databases. The primary development approach uses Docker, but frontend-only development is supported.

### Prerequisites and Environment Setup
- Requires Node.js (tested with v20.19.4) for frontend development
- Backend requires Python 3.13 (system may have 3.12, use Docker for backend)
- Docker required for full-stack development and building
- Poetry for Python dependency management (if developing backend locally)

### Quick Start Development Setup
1. Clone repository: `git clone https://github.com/joaovitoriasilva/endurain.git`
2. Navigate to project root
3. Choose development approach:
   - **Frontend Only**: See Frontend Development section below
   - **Full Stack**: Use Docker development setup

### Frontend Development (Recommended for UI changes)
- Navigate to frontend directory: `cd frontend/app`
- Install dependencies: `npm install` -- takes 21 seconds
- Build frontend: `npm run build` -- takes 9 seconds
- Start dev server: `npm run dev` -- runs on port 5173 (or 5174 if occupied)
- Format code: `npm run format` -- takes 6 seconds, ALWAYS run before committing
- **Note**: ESLint configuration needs migration to flat config format, lint command currently fails
- **Note**: No unit tests exist yet (`npm run test:unit` exits with "No test files found")

### Docker Development (Full Stack)
- Build unified image: `docker build -f docker/Dockerfile -t unified-image .`
- **CRITICAL WARNING**: Docker build may fail due to SSL certificate issues in CI environments
- **NEVER CANCEL**: Docker builds can take 15+ minutes. NEVER CANCEL. Set timeout to 60+ minutes.
- Create docker-compose.yml based on docker-compose.yml.example
- Start services: `docker compose up -d`
- Stop services: `docker compose down`

### Backend Development (Advanced)
- Backend uses Python 3.13 with Poetry for dependency management
- Located in `backend/` directory with `pyproject.toml`
- **Important**: Local backend development requires Python 3.13, use Docker if system has 3.12
- Install Poetry if needed: `pip install poetry`
- Install dependencies: `poetry install`

## Validation

### Manual Testing Validation
- **CRITICAL**: Always test login page loads correctly at `http://localhost:5173/login` or `http://localhost:5174/login`
- Verify that the Endurain logo, username/password fields, and "Sign in" button appear correctly
- Check that the footer displays version information and integration badges
- **Screenshot validation**: The application should look like a clean, modern fitness tracking login page with blue "Sign in" button and Strava/Garmin Connect compatibility badges

### Docker Validation
- If Docker builds fail with SSL errors, document the limitation but do not skip validation
- Test that built image starts correctly (even if SSL prevents building in CI)

### Pre-commit Validation
- ALWAYS run `npm run format` in frontend/app before committing
- Verify frontend builds successfully with `npm run build`
- Check that development server starts without errors

## Common Tasks

### File Locations and Structure
```
Repository root:
├── frontend/app/          # Vue.js frontend application
│   ├── package.json       # Frontend dependencies and scripts
│   ├── src/               # Vue.js source code
│   ├── dist/              # Built frontend (after npm run build)
│   └── vite.config.js     # Vite build configuration
├── backend/               # Python FastAPI backend
│   ├── pyproject.toml     # Python dependencies (Poetry)
│   └── app/               # FastAPI application code
├── docker/
│   ├── Dockerfile         # Multi-stage Docker build
│   └── start.sh           # Container entrypoint script
├── docs/                  # Documentation
├── .github/workflows/     # CI/CD pipelines
├── docker-compose.yml.example
└── .env.example
```

### Key Commands and Timing (VALIDATED)
- `npm install` (frontend): 5-21 seconds (depends on cache)
- `npm run build` (frontend): 9 seconds 
- `npm run format` (frontend): 2-6 seconds (formats all source files)
- `npm run dev` (frontend): starts in ~1 second, runs on port 5173/5174
- Docker builds: **15+ minutes, NEVER CANCEL, set 60+ minute timeouts**

### Frequently Modified Files
- Frontend components: `frontend/app/src/components/`
- Vue.js views: `frontend/app/src/views/`
- Frontend services: `frontend/app/src/services/`
- Frontend utilities: `frontend/app/src/utils/`
- API backend: `backend/app/`

### Known Issues and Limitations
- ESLint requires migration to flat config format (currently fails)
- Docker builds may fail with SSL certificate errors in CI environments
- Backend requires Python 3.13 (may not match system Python 3.12)
- No unit tests currently exist for frontend
- Frontend lint command fails, use format command instead

### Environment Variables and Configuration
- Frontend uses VITE_ENDURAIN_HOST environment variable
- Create `.env.local` in frontend/app with: `VITE_ENDURAIN_HOST=http://localhost:8080`
- Backend configuration via environment variables (see .env.example)
- Default credentials: admin/admin

### CI/CD Information
- GitHub Actions workflows in `.github/workflows/`
- Docker image builds on release and manual trigger
- Multi-architecture builds (linux/amd64, linux/arm64)
- Published to GitHub Container Registry

## Development Workflow
1. Make changes to frontend files in `frontend/app/src/`
2. Test with `npm run dev` to verify changes work
3. Run `npm run format` to format code
4. Build with `npm run build` to ensure production build works
5. For backend changes, use Docker development setup
6. Always test manually by accessing the application in browser

## Architecture Notes
- **Frontend**: Vue.js 3 with Vite, Bootstrap CSS, Chart.js, Leaflet maps
- **Backend**: Python FastAPI with SQLAlchemy, Alembic migrations
- **Database**: PostgreSQL or MariaDB support
- **Integrations**: Strava and Garmin Connect APIs
- **File Support**: .gpx, .tcx, .fit file imports
- **Authentication**: JWT tokens with 15-minute access tokens
- **Deployment**: Docker containers with multi-stage builds

Always prioritize frontend development workflow for UI changes and use Docker for full-stack development.

## Task Execution Guidelines
- **Do ONLY what is explicitly requested** - do not add extra 
  documentation, summaries, or "helpful" files unless specifically 
  asked.
- If asked to implement a feature, implement ONLY that feature - no 
  additional documentation beyond code comments.
- Do not create README files, summary documents, quick reference 
  guides, or completion reports unless explicitly requested.
- When implementing changes, focus on the code implementation itself, 
  not supplementary documentation.
- Ask for clarification if the scope is unclear rather than assuming 
  additional deliverables are wanted.

## Python Code Style Requirements

### Modern Python Syntax (Python 3.13+)
- Use modern type hint syntax: `int | None`, `list[str]`, 
  `dict[str, Any]`
- Do NOT use `typing.Optional`, `typing.List`, `typing.Dict`, etc.
- Target Python 3.13+ features and syntax

### PEP 8 Line Limits
- Code lines: **79 characters maximum**
- Comments and docstrings: **72 characters maximum**
- Enforce strictly - no exceptions

### Docstring Standard (PEP 257)
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