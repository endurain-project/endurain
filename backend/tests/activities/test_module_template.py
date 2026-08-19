"""Structural invariants of the module template.

The activities and followers modules are the pattern the remaining modules are
being refactored towards, so the rules they establish are asserted here rather
than left to review. Each is something that has already gone wrong once.
"""

import ast
from pathlib import Path

import pytest

import model_registry as app_model_registry
import modules.activities.model_registry as activities_model_registry
import modules.followers.model_registry as followers_model_registry

_MODULES_DIR = Path(__file__).resolve().parents[2] / "app" / "modules"
_APP_DIR = _MODULES_DIR.parent
_TEMPLATE_PACKAGES = sorted(
    [*(_MODULES_DIR / "activities").glob("activity*"), _MODULES_DIR / "followers"],
)


def _init_files() -> list[Path]:
    return [pkg / "__init__.py" for pkg in _TEMPLATE_PACKAGES if (pkg / "__init__.py").is_file()]


@pytest.mark.parametrize("init_file", _init_files(), ids=lambda p: p.parent.name)
def test_package_init_is_a_docstring_only(init_file: Path) -> None:
    """A package facade must not re-export its ORM, CRUD or services.

    ``from modules.activities.activity_streams import ActivityStreamsModel`` was a
    legal way to obtain the ORM model, because import-linter matches
    ``modules.activities.activity_streams.models`` and a re-export hides that
    path. Every boundary contract written against ``*.models`` / ``*.crud`` had a
    hole next to it.
    """
    tree = ast.parse(init_file.read_text())
    offenders = [
        node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom | ast.Assign | ast.AnnAssign)
    ]
    assert not offenders, (
        f"{init_file.relative_to(_MODULES_DIR.parent)} should contain only a docstring. "
        "Re-exporting from a package facade bypasses the import-linter contracts that "
        "guard *.models and *.crud — import the submodule instead."
    )


def test_every_module_exposes_one_cross_module_surface_name() -> None:
    """The surface other modules may consume is always ``integration_service``.

    Followers used to expose it as ``service``, which also held its own
    privacy-checked application logic, so "what may I depend on?" had a different
    answer per module and consumers got the internals in scope too.
    """
    missing = [
        package.relative_to(_MODULES_DIR)
        for package in _TEMPLATE_PACKAGES
        if not (package / "integration_service.py").is_file()
    ]
    assert not missing, (
        "Every independently extractable package must publish behavior through "
        f"integration_service.py; missing: {', '.join(map(str, missing))}"
    )


def test_every_persistence_package_declares_its_models() -> None:
    """A package that owns a table contributes it without a core filesystem sweep."""
    missing = [
        package.relative_to(_MODULES_DIR)
        for package in _TEMPLATE_PACKAGES
        if (package / "models.py").is_file() and not (package / "model_registry.py").is_file()
    ]
    assert not missing, (
        f"Every persistence-owning package must publish model_registry.py; missing: {', '.join(map(str, missing))}"
    )


def test_model_registries_collect_every_converted_model() -> None:
    """Registry contents match the tables owned by converted packages."""
    expected_activities = {
        f"modules.activities.{package.name}.models"
        for package in _TEMPLATE_PACKAGES
        if package.parent.name == "activities" and (package / "models.py").is_file()
    }
    assert set(activities_model_registry.MODEL_MODULES) == expected_activities
    assert set(followers_model_registry.MODEL_MODULES) == {"modules.followers.models"}
    assert (
        expected_activities | set(followers_model_registry.MODEL_MODULES) == app_model_registry._CONVERTED_MODEL_MODULES
    )


def test_core_database_does_not_discover_domain_models() -> None:
    """Model discovery belongs to app composition, never the core substrate."""
    tree = ast.parse((_APP_DIR / "core" / "database.py").read_text())
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    filesystem_scans = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"glob", "rglob"}
    }
    assert "import_all_models" not in function_names
    assert not filesystem_scans


def _template_sources() -> list[Path]:
    return sorted(
        path for package in _TEMPLATE_PACKAGES for path in package.rglob("*.py") if "__pycache__" not in path.parts
    )


def test_no_route_handler_is_async() -> None:
    """Route handlers stay ``def``, never ``async def``.

    A synchronous handler runs on Starlette's threadpool, so a blocking call
    inside it occupies one worker. The same call in an ``async def`` handler
    blocks the event loop and stalls every other request in the process. The
    provider-refresh route was exactly that bug, and nothing stops the next one
    being reintroduced by habit.
    """
    offenders = []
    for path in _template_sources():
        if "router" not in path.name:
            continue
        tree = ast.parse(path.read_text())
        offenders += [
            f"{path.relative_to(_MODULES_DIR.parent)}::{node.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and _is_route(node)
        ]

    assert not offenders, f"Route handlers must be synchronous: {', '.join(offenders)}"


def _is_route(node: ast.AsyncFunctionDef) -> bool:
    """Return whether a function carries an ``@router.<method>(...)`` decorator."""
    for decorator in node.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name) and "router" in call.value.id:
            return True
    return False


def test_http_exceptions_stay_at_the_transport_boundary() -> None:
    """Only routers and FastAPI dependencies may raise ``HTTPException``.

    Everything else raises ``core.exceptions``. The ``persistence-no-http``
    import contract covers CRUD, but services and subscribers are equally capable
    of coupling themselves to HTTP — and a subscriber that does is running in the
    durable-job worker, which serves no HTTP at all.
    """
    allowed = {"router.py", "public_router.py", "dependencies.py"}
    offenders = []
    for path in _template_sources():
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            call = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = call.id if isinstance(call, ast.Name) else getattr(call, "attr", "")
            if name == "HTTPException":
                offenders.append(f"{path.relative_to(_MODULES_DIR.parent)}:{node.lineno}")

    assert not offenders, f"Raise a core.exceptions error instead of HTTPException: {', '.join(offenders)}"


_LOG_METHODS = {"debug", "info", "warning", "error", "critical", "exception", "log"}


def _log_message_arg(node: ast.Call) -> ast.expr | None:
    """Return the message argument of a ``logger.<level>(...)`` call, if it is one."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in _LOG_METHODS:
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "logger":
        return None
    # logger.log() takes the level first, so the message is the second argument.
    index = 1 if func.attr == "log" else 0
    return node.args[index] if len(node.args) > index else None


def test_log_messages_are_static_strings() -> None:
    """Variable data belongs in ``extra=core_logger.context(...)``, not the message.

    An f-string message is a distinct string per occurrence, so the records cannot
    be grouped, counted or alerted on, and the interpolated values are not
    queryable fields. It is also how identifiers end up in messages that get
    truncated or scrubbed downstream.
    """
    offenders = []
    for path in _template_sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            message = _log_message_arg(node)
            if isinstance(message, ast.JoinedStr) or (
                isinstance(message, ast.BinOp) and isinstance(message.op, ast.Mod)
            ):
                offenders.append(f"{path.relative_to(_MODULES_DIR.parent)}:{node.lineno}")

    assert not offenders, (
        "Log messages must be static strings; pass variable data as "
        f"extra=core_logger.context(...): {', '.join(offenders)}"
    )


def test_event_subscribers_log_what_they_did() -> None:
    """Every ``*_for_event`` handler logs, so derived work is not silent.

    These run outside a request — on the bus consumer or a job worker — where
    ``best_effort`` records failures but a *successful* no-op leaves no trace at
    all. "The activity imported but has no thumbnail" was unanswerable from the
    logs: nothing distinguished 'skipped, too few waypoints' from 'never ran'.
    """
    offenders = []
    for path in _template_sources():
        if not path.name.endswith("subscribers.py"):
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.endswith("_for_event"):
                continue
            logs = any(isinstance(inner, ast.Call) and _log_message_arg(inner) is not None for inner in ast.walk(node))
            if not logs:
                offenders.append(f"{path.relative_to(_MODULES_DIR.parent)}::{node.name}")

    assert not offenders, f"Event handlers must log their outcome: {', '.join(offenders)}"
