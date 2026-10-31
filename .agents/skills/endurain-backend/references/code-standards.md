# Code standards

## Python
- Python 3.13 syntax: `int | None`, `list[str]`; no `typing.Optional/List/Dict`.
- Lines up to 120 characters, code and prose alike (the formatter does not wrap docstrings; keep paragraphs readable).
- Imports grouped stdlib / third-party / local; `TYPE_CHECKING` to avoid cycles.
- Every module has a top-level docstring.
- Comments and docstrings state what the code does now and why. History (what it "used to" do, how much duplication a refactor removed) goes in the commit message.
- Parameter order, `__init__.py`, comment content, naming and layering are stated once in `docs/developer-guide/module-structure.md`; this file only holds the language- and framework-level style below.

## Docstrings (PEP 257, Google sections)
Enforced by ruff `D` with `convention = "google"` on the converted modules (`activities`, `followers`); other modules are exempt until converted.
- Summary on the opening line, then a blank line, then sections.
- Every public module, class, function and method has a docstring.
- `Args`: every parameter of a public function (D417 enforces it once a section exists). A `_private` helper gets a summary and `Args` only for a non-obvious parameter.
- `Returns`: when a value comes back. `Returns: None.` is not required.
- `Raises`: the exceptions the function raises or deliberately lets propagate, and especially the ones that carry a security meaning (`PermissionDeniedError`, `NotFoundError` as an anti-enumeration answer). Omit it when there are none; do not write `Raises: None.`.
- Classes: summary plus `Attributes`.
- No examples; extended explanation only where the *why* is not obvious from the code.
- A docstring is not a design document: what, then why, in the fewest lines. Rationale that spans a
  module belongs in the guide, and history in the commit message.
- A docstring with backslashes is a raw string (`r"""`).

## SQLAlchemy 2
- `Mapped[...]` with `mapped_column()`; every column typed.
- `crud` stages with `db.flush()`; only `service` commits. `db.refresh(obj)` after the flush when you need server defaults.
- Persistence raises `core.exceptions`; the app handler maps them to responses. Converted modules do not use `@handle_db_errors`: a `SQLAlchemyError` propagates to `core.exceptions.database_error_handler`.

## Pydantic v2
- `ConfigDict`, `field_validator`; no class `Config`, no `@validator`.
- Keep ORM and schema names distinct.
- A `<Thing>Read` has a required `id`; input shapes are `<Thing>Create` in `contracts.py` (see the guide's "Read models are stored rows").

## FastAPI
- `response_model` on every JSON endpoint; a route that returns bytes declares `responses=` with its media type instead (`TestRouteConventions`). Status 200 (GET), 201 (POST create), 202 (POST accepted for background processing), 204 (DELETE).
- Auth through `Depends()`.
- Constrain a path or query parameter on its type (`core.dependencies.PositiveId`, an enum, `AfterValidator`), not with a `Depends` function that raises `HTTPException`; `TestRouteConventions` fails on one in a converted module.
- Endpoint docstring says what, not how. It is exempt from `Args`/`Returns`/`Raises`: FastAPI publishes it as the OpenAPI description and it is copied into `api.generated.ts`, so parameter names such as `_check_scopes` would become public API text.
- Route handlers are plain `def`, never `async def` (a blocking call in an async handler stalls the event loop; `test_no_route_handler_is_async`). Handle uploads with `core.file_uploads.save_validated_upload_sync`.

## Logging
Use `core.logger.get_logger(__name__)` and `core.logger.context(...)`; never f-string values into messages.

| Layer | Logs |
| --- | --- |
| `router`, `public_router` | nothing (a rejected capability token is logged by the `service` that verifies it) |
| `service` | INFO state change completed; WARNING request refused; DEBUG inputs to a non-obvious decision. A function that raises `PermissionDeniedError` or `AccessConcealedError` logs a WARNING in the same function, and one that ends a transaction logs in the same function; a service that only delegates logs nothing |
| `crud` | only what it swallows: ERROR cannot complete, WARNING absorbed anomaly; never success narration |
| `subscribers` | DEBUG when skipping, ERROR when failing |
| `query`, `serializers`, `signing`, `models`, `schema`, pure utils | nothing |
| a file named for no role | nothing, unless listed with its reason in `_HELPERS_THAT_LOG` |

`console=True` only for operator-facing events (migrations, bulk import progress), enforced by `test_console_is_for_operator_events`.
