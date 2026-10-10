---
description: 'Python 3.13 + FastAPI + SQLAlchemy + Alembic coding standards, docstring format, testing patterns, and module organization for the Endurain backend'
applyTo: '**/*.py'
---
# Project Context
- **Python Version:** 3.13+ (required)
- **Framework:** FastAPI with SQLAlchemy ORM and Alembic migrations
- **Dependency Management:** uv (see `backend/pyproject.toml`)
- **Project Structure:** All backend code in `backend/app/`
- **Testing Framework:** Tests must be in `backend/tests/` directory and follow the project structure like best practices.

# Development Setup
- **Install uv:** Follow the official uv installation instructions
- **Install dependencies:** `uv sync` (in `backend/` 
  directory)
- **Use Docker:** If system Python < 3.13, use Docker for 
  development

# SQLAlchemy 2.0 Standards
- **Use Mapped types:** `Mapped[int]`, `Mapped[str | None]`
- **Use mapped_column():** Not `Column()` - modern declarative 
  syntax
- **Type all columns:** Every column must have type annotation
- **Refresh after commits:** Always `db.refresh(obj)` after 
  `db.commit()`
- **Specific exceptions:** Use `HTTPException`, not broad 
  `Exception`

# Pydantic v2 Standards
- **Use ConfigDict:** Not class-based `Config`
- **Use field_validator:** Not `@validator` decorator
- **Clear schema hierarchy:** Avoid ORM/Schema naming 
  confusion
- **All endpoints need response_model:** No untyped responses

# FastAPI Endpoint Standards
- **response_model required:** All endpoints must specify 
  return type
- **Proper status codes:** 200 (GET), 201 (POST), 204 
  (DELETE)
- **Security dependencies:** Use `Depends()` for auth checks
- **Docstrings:** Describe what endpoint does, not how

# Security Requirements
- **File validation:** Use `safeuploads` library for type 
  checking
- **Input sanitization:** Prevent XSS, SQL injection
- **File size limits:** Enforce max sizes on uploads
- **No hardcoded secrets:** Use environment variables
- **Async file I/O:** Use `await file.read()`, not sync

# Modern Python Syntax (Python 3.13+)
- Use modern type hint syntax: `int | None`, `list[str]`, 
  `dict[str, Any]`
- Do NOT use `typing.Optional`, `typing.List`, `typing.Dict`, etc.
- Target Python 3.13+ features and syntax
- Always prioritize readability and clarity

# PEP 8 Line Limits
- Code lines: **120 characters maximum**
- Comments and docstrings: **72 characters maximum**
- Enforce strictly - no exceptions

# Docstring Standard (PEP 257)
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

# Logging by layer

Use `core.logger.get_logger(__name__)` and pass structured fields through
`core.logger.context(...)` — never f-string the values into the message.

Each layer logs one kind of thing, so a reader knows where to look and the same
event is never reported twice:

| Layer | Logs |
| --- | --- |
| `router` / `public_router` | **Nothing.** It knows nothing the service does not, and the request itself is already correlated by the request-id middleware. The one exception is a rejected capability token on an unauthenticated blob route: that is an authentication failure with no service beneath it to report it. |
| `service` | The decision layer. **INFO** when a state change completed (created / updated / deleted / queued). **WARNING** when a request was refused (permission, precondition, invalid input). **DEBUG** for the inputs to a non-obvious decision — a resolved anchor date, a page window, why a read came back empty. |
| `crud` | **Only what it swallows.** ERROR for a failure it cannot complete; WARNING for an anomaly it absorbs (a caught `IntegrityError`, a row that vanished mid-operation) — the caller sees a normal return and would otherwise never learn of it. Never DEBUG/INFO narrating successful work: the service already said what happened, and repeating it here does so at query volume. |
| `subscribers` | **DEBUG** when skipping (why it did nothing) and **ERROR** when failing. They run detached from any request, so silence is indistinguishable from never having run. |
| `query`, `serializers`, `signing`, `models`, `schema`, pure utils | **Nothing.** They make no decisions and own no failures. |

`console=True` in `context(...)` mirrors a record to the container log; reserve it
for operator-facing events (startup, migrations, bulk import progress).

# Testing Standards (pytest)
- **Location:** `backend/tests/` mirroring `backend/app/` 
  structure
- **Naming:** `test_*.py` per module, group in test classes
- **Target:** 100% coverage, use fixtures from `conftest.py`

## CRITICAL: SQLAlchemy Model Testing
**Never instantiate models** - causes relationship errors.
Use attribute inspection:
```python
assert MyModel.id.default.arg == 1
assert MyModel.name.nullable is False
assert MyModel.count.type.python_type == int
```

## Mocking & Testing Patterns
- **AsyncMock:** async functions, **MagicMock:** sync objects
- **@patch:** external dependencies (logging, DB calls)
- **Edge cases:** Empty/None, nonexistent entities, errors, 
  malformed input
- **Exceptions:** `with pytest.raises(HTTPException) as exc_info`
- **Skip tests:** Only when necessary, document with `reason=`
- **Async tests:** Use `async def test_*`, check with 
  `assert_awaited_once()`

## Coverage Verification
```bash
uv run pytest tests/module/ -v
uv run pytest tests/module/ --cov=app/module \
  --cov-report=term-missing
```

# Module Organization Standards
- **__init__.py exports:** Define `__all__` list explicitly
- **Module docstrings:** Every module needs top-level 
  docstring
- **Import organization:** Group by stdlib, third-party, local
- **Avoid circular imports:** Use TYPE_CHECKING for type hints
- **Clear file structure:** models, schemas, crud, routers, 
  utils