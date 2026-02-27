---
description: 'Conduct a comprehensive code quality audit of a backend module against modern standards and best practices'
agent: 'agent'
tools: ['search', 'read/readFile']
argument-hint: 'Module name to audit (e.g. activities, gears, users)'
---

# Backend Module Code Quality Audit

## Mission

Conduct a comprehensive code quality audit of the **`${input:module:Module name to audit (e.g. activities, gears, users)}`** module. Skip any module that has already been audited (check for existing audit notes or confirmed compliance).

## Scope & Preconditions

- Target path: `backend/app/${input:module}/`
- All files in the module must be analyzed: `__init__.py`, `models.py`, `schema.py`, `crud.py`, `router.py`, `utils.py`, and any additional files present.
- Modules previously audited and confirmed compliant: `user_privacy_settings`, `user_goals`, `user_identity_providers`, `server_settings`, `health`.
- If the module does not exist, stop and report the missing path.

## Workflow

### 1. Discovery

- List all files inside `backend/app/${input:module}/`.
- Read each file fully before forming any findings.
- Perform a codebase-wide grep for ORM attribute mutations (e.g., `model_instance.attribute =`) originating outside CRUD files.

### 2. Analysis Dimensions

Evaluate every file against the following dimensions:

#### Modern Framework Standards

- **SQLAlchemy 2.0:** `Mapped[Type]` with `mapped_column()`, declarative syntax, 2.0-style query API (`select()`, `scalars()`). No legacy `Column()` or `Query` usage.
- **Pydantic v2:** `ConfigDict`, `StrictInt`/`StrictStr`/`StrictFloat`/`StrictBool`, `field_validator`, `model_validate`, field constraints (`max_length`, `pattern`, `ge`, `le`).
- **Python 3.13+:** Full type hints, modern union syntax (`X | Y`), no `Optional[X]` where `X | None` suffices.

#### Code Quality & Best Practices

- Module-level docstrings at the top of every file.
- Complete type hints on all function signatures (parameters and return types).
- PEP 257 docstrings with `Args`, `Returns`, and `Raises` sections on all public functions and methods.
- PEP 8 compliance: line length ≤ 79 characters, `snake_case` naming.
- Specific exception handling — no bare `except Exception`.
- DRY principle — no duplicated logic across files.

#### Architecture & Patterns

- Clean separation of concerns: models / schemas / CRUD / routes.
- No ORM object mutation outside CRUD files (`delattr()`, direct attribute assignment).
- All API endpoints have an explicit `response_model`.
- FastAPI dependency injection used consistently.
- Functions that receive ORM model instances must have ORM type hints, not Pydantic schema hints.

#### Performance & Data Integrity

- `db.refresh()` called after every `db.commit()` where the refreshed data is subsequently used.
- No synchronous I/O inside `async` functions.
- Eager vs. lazy relationship loading evaluated for N+1 query risk.
- Proper transaction rollback on errors.

#### Security & Validation

- File uploads: magic-number validation, size limits, no directory traversal.
- Input sanitization: SQL injection prevention via parameterized queries only.
- Authentication/authorization: correct scope and permission checks on every endpoint.
- No hardcoded secrets or credentials.

### 3. Findings Classification

For each finding, record:

| Field | Value |
|-------|-------|
| File | Relative path |
| Category | Models / Schemas / CRUD / Router / Utils / Module |
| Issue | Short description |
| Priority | 🔴 High / 🟡 Medium / 🟢 Low |
| Status | ✅ DONE / ⚠️ PENDING / ❌ NEEDS FIX |

### 4. Reporting

Structure the output as follows:

```markdown
## [MODULE_NAME] Module Audit

### Summary
- Files analyzed: X
- Issues found: Y
- High priority: Z

### Issues by Priority

#### 🔴 High Priority
1. **[Issue Title]**
   - File: `path/to/file.py`
   - Current:
     ```python
     # existing code snippet
     ```
   - Recommended:
     ```python
     # improved code snippet
     ```
   - Impact: [explanation]
   - Status: ⚠️ PENDING

#### 🟡 Medium Priority
[Same format]

#### 🟢 Low Priority
[Same format]

### Status Table

| File | Category | Issue | Priority | Status | Impact |
|------|----------|-------|----------|--------|--------|

### Completion Progress
- ✅ Completed: X / Y
- ⚠️ Pending: Z / Y
```

## Output Expectations

- Deliver the full audit report in Markdown inside the chat response.
- Provide **before/after code snippets** for every High and Medium priority issue.
- Do **not** apply any file edits automatically — report findings only, unless the user explicitly requests fixes after reviewing the report.
- If no issues are found in a dimension, state that explicitly rather than omitting the section.

## Quality Assurance

After generating the report, verify:

- [ ] Every file in the module has been analyzed.
- [ ] ORM mutation grep was performed codebase-wide, not just within the module.
- [ ] All endpoints have a `response_model` entry in the status table.
- [ ] No hardcoded secrets were found (or confirmed absent).
- [ ] Priority levels are consistent with impact descriptions.

## Related Resources

- [Module Audit Prompt Template](../../devdocs/MODULE_AUDIT_PROMPT_TEMPLATE.md)
- [Python Coding Standards](../instructions/python.instructions.md)
- [Security Guidelines](../instructions/security-and-owasp.instructions.md)
- [SQLAlchemy 2.0 Migration Guide](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
