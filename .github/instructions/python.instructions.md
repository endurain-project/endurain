---
applyTo: '**/*.py'
---
# Project Context
- **Python Version:** 3.13+ (required)
- **Framework:** FastAPI with SQLAlchemy ORM and Alembic migrations
- **Dependency Management:** Poetry (see `backend/pyproject.toml`)
- **Project Structure:** All backend code in `backend/app/`
- **Testing Framework:** Tests must be in `backend/tests/` directory and follow the project structure like best practices.

# Development Setup
- **Install Poetry:** `pip install poetry`
- **Install dependencies:** `poetry install` (in `backend/` 
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
- Code lines: **79 characters maximum**
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
poetry run pytest tests/module/ -v
poetry run pytest tests/module/ --cov=app/module \
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