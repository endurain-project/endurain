"""Structural invariants of the module template.

The activities and followers modules are the pattern the remaining modules are
being refactored towards, so the rules they establish are asserted here rather
than left to review. Each is something that has already gone wrong once.
"""

import ast
from pathlib import Path

import pytest
from tests._helpers.module_roles import CONVERTED_MODULES

import model_registry as app_model_registry
import module_registry as runtime_module_registry
import modules.activities.contributor_registry as activities_contributor_registry
import modules.activities.model_registry as activities_model_registry
import modules.followers.model_registry as followers_model_registry

_MODULES_DIR = Path(__file__).resolve().parents[2] / "app" / "modules"
_APP_DIR = _MODULES_DIR.parent


def _template_packages() -> list[Path]:
    """Return the independently extractable packages of every converted module.

    A composition namespace contributes its child packages; a flat module is its own
    package. Derived from ``CONVERTED_MODULES`` so converting a module covers it here
    without a second list to update.
    """
    found: list[Path] = []
    for name in CONVERTED_MODULES:
        root = _MODULES_DIR / name
        children = [child for child in sorted(root.iterdir()) if child.is_dir() and (child / "__init__.py").is_file()]
        found.extend(children or [root])
    return found


_TEMPLATE_PACKAGES = _template_packages()


def _absolute_imports(path: Path) -> set[str]:
    """Return absolute modules imported by a Python source file."""
    imports: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
    return imports


#: Packages that publish no cross-module operation, as ``{package name: reason}``.
#: Only a package no other module calls may be listed: an empty
#: ``integration_service.py`` would promise a surface that does not exist. The
#: test below fails on an entry that has grown a surface, so the list cannot
#: outlive the exemption.
_NO_CROSS_MODULE_SURFACE: dict[str, str] = {
    "activity_geocoding": (
        "Purely reactive: it geocodes on the activity.created event (subscribers) and "
        "reconciles on a schedule (scheduled_jobs), both wired by app/module_registry.py. "
        "Nothing outside the package calls it."
    ),
}


def test_every_module_exposes_one_cross_module_surface_name() -> None:
    """The surface other modules may consume is always ``integration_service``.

    Followers used to expose it as ``service``, which also held its own
    privacy-checked application logic, so "what may I depend on?" had a different
    answer per module and consumers got the internals in scope too.
    """
    missing = [
        package.relative_to(_MODULES_DIR)
        for package in _TEMPLATE_PACKAGES
        if package.name not in _NO_CROSS_MODULE_SURFACE and not (package / "integration_service.py").is_file()
    ]
    assert not missing, (
        "Every independently extractable package must publish behavior through "
        f"integration_service.py; missing: {', '.join(map(str, missing))}"
    )


def test_exempt_packages_publish_no_surface() -> None:
    """An exemption is for a package with no surface; delete it once one exists."""
    stale = [
        name
        for name in _NO_CROSS_MODULE_SURFACE
        if (_MODULES_DIR / "activities" / name / "integration_service.py").is_file()
    ]
    assert not stale, f"Remove from _NO_CROSS_MODULE_SURFACE, they now have a surface: {', '.join(stale)}"


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


@pytest.mark.parametrize(
    ("relative_path", "allowed_child_imports"),
    [
        ("activities/activity/ingestion_service.py", set()),
        (
            "users/users_profile/export_service.py",
            {
                "modules.activities.activity_file_storage.integration_service",
                "modules.activities.activity_media.integration_service",
            },
        ),
        (
            "users/users_profile/import_service.py",
            {
                "modules.activities.activity_file_storage.integration_service",
                "modules.activities.activity_media.integration_service",
            },
        ),
    ],
)
def test_activity_orchestrators_do_not_enumerate_child_packages(
    relative_path: str,
    allowed_child_imports: set[str],
) -> None:
    """Root orchestration depends on contributors, not child JSON packages."""
    path = _MODULES_DIR / relative_path
    child_imports = {
        imported
        for imported in _absolute_imports(path)
        if imported.startswith("modules.activities.activity_")
        and not imported.startswith("modules.activities.activity.contracts")
        and not imported.startswith("modules.activities.activity.integration_service")
        and not imported.startswith("modules.activities.activity.schema")
    }
    assert child_imports == allowed_child_imports
    assert "modules.activities.contributor_registry" in _absolute_imports(path)


def test_installed_activity_contributor_keys_are_unique_per_kind() -> None:
    """App composition installs every stable contributor key exactly once."""
    runtime_module_registry.configure_activity_contributors()
    groups = (
        activities_contributor_registry.activity_ingestion_contributors(),
        activities_contributor_registry.file_ingestion_contributors(),
        activities_contributor_registry.profile_activity_contributors(),
        activities_contributor_registry.profile_global_contributors(),
    )
    for group in groups:
        keys = [contributor.key for contributor in group]
        assert keys
        assert len(keys) == len(set(keys))


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

    Everything else raises ``core.exceptions``. ``TestLayerRules`` covers the
    persistence layer, but services and subscribers are equally capable
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
