"""The logging-by-layer rule from ``.agents/skills/endurain-backend/references/code-standards.md``, enforced.

A convention that only exists in prose drifts: before this, CRUD modules narrated
every successful read and write at DEBUG — duplicating what the service already
reported, at query volume — while four services logged nothing at all. These
assertions are what keep the layers saying one kind of thing each.
"""

import ast
import pathlib
import re

from tests._helpers.module_roles import CONVERTED_MODULES, files_with_role, role_of

#: Modules the logging rule has been applied to — the shared
#: ``CONVERTED_MODULES`` list in ``tests/_helpers/module_roles.py``, so
#: converting a module is a single edit there.
_CONVERTED = tuple(pathlib.Path("app/modules") / name for name in CONVERTED_MODULES)

# Layers whose logging level set is fixed by the rule.
_ALLOWED: dict[str, set[str]] = {
    # Persistence reports only what it swallows: a failure it cannot complete,
    # or an anomaly it absorbs behind a normal-looking return.
    "crud": {"warning", "error"},
    # Detached from any request, so a skip must say why and a failure must shout.
    "subscribers": {"debug", "error", "warning"},
    # No decisions, no failures of their own.
    "query": set(),
    "serializers": set(),
    "signing": set(),
    "models": set(),
    "schema": set(),
    "contracts": set(),
}

#: Roles that may log at all. Anything else (``query``, ``serializers``, ``signing``, ``models``,
#: ``schema``, ``contracts``, ``constants``, ``events``, routers) logs nothing; the roles above carry their
#: own level limits. A file whose name declares no role is not trusted: it must be listed in
#: ``_HELPERS_THAT_LOG`` with the reason, so a new helper cannot log unnoticed.
_MAY_LOG = frozenset(
    {
        "service",
        "crud",
        "subscribers",
        "scheduled_jobs",
        "dependencies",
        "integration_service",
        "migration_service",
    }
)

#: Role-less helper files that log, as ``{path relative to modules/: reason}``. The test fails on an
#: entry that no longer logs, so the register shrinks rather than lingers.
_HELPERS_THAT_LOG: dict[str, str] = {
    "activities/activity/stats.py": "Skips a malformed row it cannot attribute to a sport and says so.",
    "activities/activity_file_import/adapter.py": "Names the parser that produced a result, for diagnosing a missing chart.",
    "activities/activity_file_import/fit_frames.py": "Parser anomalies the file itself carries.",
    "activities/activity_file_import/fit_utils.py": "Parser anomalies the file itself carries.",
    "activities/activity_file_import/gpx_utils.py": "Parser anomalies the file itself carries.",
    "activities/activity_file_import/tcx_utils.py": "Parser anomalies the file itself carries.",
    "activities/activity_ingestion/background.py": "Owns the in-process pool, whose failures nothing else would see.",
    "activities/activity_thumbnail/render.py": "A failed render returns ``None``; the reason has to be said here.",
}

#: Modules whose ``console=True`` records are operator-facing: bulk-import progress and migrations.
_CONSOLE_ALLOWED_PREFIXES = ("activities/activity_ingestion/",)
_CONSOLE_ALLOWED_ROLES = frozenset({"migration_service"})

#: Exceptions a service raises to refuse a request. Raising one is a decision, and the rule says a refusal
#: is a WARNING. ``AccessConcealedError`` is a refusal answered as ``404``; plain ``NotFoundError`` is
#: deliberately absent: it reports a record that is missing (or whose absence cannot be told from a refusal),
#: which is not a decision about the caller.
_REFUSALS = frozenset({"PermissionDeniedError", "AccessConcealedError"})

_ROOT = pathlib.Path("app/modules")


def _log_calls(path: pathlib.Path) -> list[str]:
    """Return the log levels used in a module."""
    return re.findall(r"logger\.(debug|info|warning|error|exception|critical|log)\(", path.read_text())


def _modules_named(stem: str) -> list[pathlib.Path]:
    """Return every converted module whose file plays the given role."""
    return files_with_role(_CONVERTED, stem)


def _converted_files() -> list[pathlib.Path]:
    """Return every Python file of every converted module."""
    return sorted(
        path
        for root in _CONVERTED
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    )


def _relative(path: pathlib.Path) -> str:
    """Return a path relative to ``app/modules`` in posix form."""
    return path.relative_to(_ROOT).as_posix()


def _function_logs(function: ast.AST) -> bool:
    """Return whether a function body calls a logger method."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
        for node in ast.walk(function)
    )


def _function_warns(function: ast.AST) -> bool:
    """Return whether a function body logs at WARNING or above."""
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
        and node.func.attr in {"warning", "error", "exception", "critical"}
        for node in ast.walk(function)
    )


def _refuses(function: ast.AST) -> bool:
    """Return whether a function raises one of the refusal exceptions."""
    for node in ast.walk(function):
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name in _REFUSALS:
                return True
    return False


def _commits(function: ast.AST) -> bool:
    """Return whether a function ends a transaction or hands ``commit`` to a publisher."""
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
                return True
            if any(keyword.arg == "commit" for keyword in node.keywords):
                return True
    return False


class TestLoggingRule:
    def test_crud_never_narrates_success(self):
        """The service already said what happened; repeating it here is noise."""
        offenders = [
            f"{p}: {sorted(set(_log_calls(p)) - _ALLOWED['crud'])}"
            for p in _modules_named("crud")
            if set(_log_calls(p)) - _ALLOWED["crud"]
        ]

        assert offenders == []

    def test_subscribers_only_skip_or_fail(self):
        """A subscriber says why it skipped (DEBUG) or that it failed; success narration is noise."""
        offenders = [
            f"{p}: {sorted(set(_log_calls(p)) - _ALLOWED['subscribers'])}"
            for p in _modules_named("subscribers")
            if set(_log_calls(p)) - _ALLOWED["subscribers"]
        ]

        assert offenders == []

    def test_routers_delegate_their_logging_too(self):
        offenders = [str(p) for stem in ("router", "public_router") for p in _modules_named(stem) if _log_calls(p)]

        assert offenders == []

    def test_pure_layers_do_not_log(self):
        offenders = [
            f"{p}: {sorted(set(_log_calls(p)))}"
            for stem in ("query", "serializers", "signing", "models", "schema", "contracts")
            for p in _modules_named(stem)
            if _log_calls(p)
        ]

        assert offenders == []

    def test_only_listed_files_log(self):
        """A file logs because its role may, or because it is listed with a reason.

        The role vocabulary is open, so a helper named for no role would otherwise be
        trusted by default; the register makes every such file state why it logs.
        """
        offenders = [
            _relative(path)
            for path in _converted_files()
            if _log_calls(path) and role_of(path.stem) not in _MAY_LOG and _relative(path) not in _HELPERS_THAT_LOG
        ]
        stale = [name for name in _HELPERS_THAT_LOG if not _log_calls(_ROOT / name)]

        assert not offenders, (
            "These files log but declare no role that may. Name the file for its role, or list it in "
            "_HELPERS_THAT_LOG with the reason:\n  " + "\n  ".join(offenders)
        )
        assert not stale, "These helpers no longer log; remove them from _HELPERS_THAT_LOG:\n  " + "\n  ".join(stale)

    def test_console_is_for_operator_events(self):
        """``console=True`` is bulk-import progress and migrations, not request or persistence noise."""
        offenders = [
            _relative(path)
            for path in _converted_files()
            if "console=True" in path.read_text()
            and not _relative(path).startswith(_CONSOLE_ALLOWED_PREFIXES)
            and role_of(path.stem) not in _CONSOLE_ALLOWED_ROLES
        ]

        assert offenders == []

    def test_a_service_decision_is_logged(self):
        """A refusal and a state change leave a trace, wherever the function sits.

        The rule is on what a function *does*: raising ``PermissionDeniedError`` or ending a transaction without a log line is the invisible
        decision. A service that only delegates has no such function, so it needs no exemption.
        """
        offenders: list[str] = []
        for path in _modules_named("service"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if _refuses(node) and not _function_warns(node):
                    offenders.append(f"{_relative(path)}::{node.name} (refusal without a WARNING)")
                elif _commits(node) and not _function_logs(node):
                    offenders.append(f"{_relative(path)}::{node.name} (state change without a log)")

        assert offenders == [], "Log the refusal (WARNING) or the state change in the same function:\n  " + "\n  ".join(
            offenders
        )
