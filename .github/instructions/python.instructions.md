---
applyTo: '**/*.py'
---
# Project Context
- **Python Version:** 3.13+ (required)
- **Framework:** FastAPI with SQLAlchemy ORM and Alembic migrations
- **Dependency Management:** Poetry (see `backend/pyproject.toml`)
- **Project Structure:** All backend code in `backend/app/`

# Development Setup
- **Install Poetry:** `pip install poetry`
- **Install dependencies:** `poetry install` (in `backend/` 
  directory)
- **Use Docker:** If system Python < 3.13, use Docker for 
  development

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