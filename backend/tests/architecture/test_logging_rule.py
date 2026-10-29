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

import core.exceptions as core_exceptions

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
    "activities/activity_file_import/adapter.py": "Names the parser that produced a result, for diagnosing a missing chart.",
    "activities/activity_file_import/fit_frames.py": "Parser anomalies the file itself carries.",
    "activities/activity_file_import/fit_utils.py": "Parser anomalies the file itself carries.",
    "activities/activity_file_import/gpx_utils.py": "Parser anomalies the file itself carries.",
    "activities/activity_file_import/tcx_utils.py": "Parser anomalies the file itself carries.",
    "activities/activity_thumbnail/render.py": "A failed render returns ``None``; the reason has to be said here.",
    "strava/rate_limit_store.py": "Reports a rate limit it records or a storage outage it tolerates; the caller only sees a bool.",
    "garmin/mfa_code_store.py": "Reports a storage outage and a code it could not delete, which have no caller to tell.",
    "auth/identity_providers/refresh_claim_store.py": "Reports a storage outage it tolerates by failing open; the caller only sees a bool.",
    "auth/identity_providers/token_policy.py": "Reports a token the age policy retires or a link with no timestamp; the caller only sees the action.",
    "auth/mfa/setup_store.py": "Reports a setup secret it could not decrypt; the caller only sees None.",
    "garmin/token_utils.py": "Reports a token it could not decrypt or a session Garmin rejected; the caller only sees None.",
    "users/users_profile/utils.py": (
        "Reports a memory probe or an auto-config it cannot complete and falls back to defaults; the caller only sees the defaults."
    ),
    "websocket/manager.py": "Owns the connection registry; an eviction and a failed send have no caller to report to.",
    "websocket/ticket_store.py": "Reports a storage outage and an unreadable ticket value it cannot attribute to a request.",
}

#: Modules whose ``console=True`` records are operator-facing: bulk-import progress (including the Strava export and gear CSV imports), migrations and the boot
#: import of deprecated settings.
_CONSOLE_ALLOWED_PREFIXES = (
    "activities/activity_ingestion/",
    "server_settings/",
    "strava/bulk_import_service.py",
    "strava/gear_service.py",
)
_CONSOLE_ALLOWED_ROLES = frozenset({"migration_service"})

#: Exceptions a service raises to refuse a request. Raising one is a decision, and the rule says a refusal
#: is a WARNING. ``AccessConcealedError`` is a refusal answered as ``404``; ``UnauthenticatedError`` is a
#: credential the service refused. Plain ``NotFoundError`` is deliberately absent: it reports a record that is
#: missing (or whose absence cannot be told from a refusal), which is not a decision about the caller. So are
#: ``ConflictError`` and ``InvalidInputError``: an ordinary client mistake is not logged above DEBUG.
_REFUSALS = frozenset({"PermissionDeniedError", "AccessConcealedError", "UnauthenticatedError"})

_ROOT = pathlib.Path("app/modules")

#: Files whose broad ``except Exception`` handler logs without a traceback on purpose, as ``{path: reason}``
#: relative to ``app/``.
_BROAD_EXCEPT_WITHOUT_TRACEBACK: dict[str, str] = {
    "core/config.py": "Reads a secret file at import time; the exception text names the file, which must not be logged.",
}

#: Files that log at INFO inside a loop on purpose, as ``{path: reason}`` relative to ``app/``. A loop that
#: reports each item floods the log at the size of the data; it logs the item at DEBUG and one summary at INFO.
_INFO_IN_LOOP: dict[str, str] = {
    "core/network.py": "Boot-time resolution of the configured trusted proxies and an audited allowlist hit.",
    "main.py": "Names each startup task once, at boot.",
}
_INFO_IN_LOOP_EXEMPT_DIRS = ("migrations", "alembic")

_APP = pathlib.Path("app")


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
    """Return whether a function builds or raises one of the refusal exceptions."""
    for node in ast.walk(function):
        target = None
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        elif isinstance(node, ast.Call):
            target = node.func
        if target is None:
            continue
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name in _REFUSALS:
            return True
    return False


def _is_logger_call(node: ast.AST) -> bool:
    """Return whether a node is a call on the module ``logger``."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    )


def _app_files() -> list[pathlib.Path]:
    """Return every Python file of the application, vendored migrations excluded."""
    return sorted(p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts)


def _own_nodes(handler: ast.ExceptHandler):
    """Yield the nodes of an ``except`` body, leaving nested handlers to be judged on their own."""
    stack = list(handler.body)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(child for child in ast.iter_child_nodes(node) if not isinstance(child, ast.ExceptHandler))


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

    def test_a_failure_log_names_its_exception_the_project_way(self):
        """``exc_info=err``, never ``exc_info=True``: the handler binds the exception it reports."""
        offenders = [
            f"{path}:{node.lineno}"
            for path in _app_files()
            for node in ast.walk(ast.parse(path.read_text()))
            if _is_logger_call(node)
            for keyword in node.keywords
            if keyword.arg == "exc_info" and isinstance(keyword.value, ast.Constant)
        ]

        assert offenders == [], "Bind the exception (`except ... as err`) and pass exc_info=err:\n  " + "\n  ".join(
            offenders
        )

    def test_an_unexpected_failure_keeps_its_traceback(self):
        """A broad ``except Exception`` that logs a warning or an error carries the traceback with it."""
        offenders: list[str] = []
        for path in _app_files():
            if "alembic" in path.parts or path.relative_to(_APP).as_posix() in _BROAD_EXCEPT_WITHOUT_TRACEBACK:
                continue
            for handler in ast.walk(ast.parse(path.read_text())):
                if not isinstance(handler, ast.ExceptHandler):
                    continue
                caught = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
                if not any(isinstance(t, ast.Name) and t.id in {"Exception", "BaseException"} for t in caught):
                    continue
                offenders.extend(
                    f"{path}:{node.lineno}"
                    for node in _own_nodes(handler)
                    if _is_logger_call(node)
                    and node.func.attr in {"warning", "error", "critical"}
                    and not any(keyword.arg == "exc_info" for keyword in node.keywords)
                )

        assert offenders == [], "Pass exc_info=err so the traceback is kept:\n  " + "\n  ".join(offenders)

    def test_a_server_failure_raised_onwards_is_logged_once(self):
        """A block that raises a 5xx domain error leaves the ERROR log to the boundary that answers for it.

        The HTTP error handler, the durable job runner and the in-process pool each log a failure that reaches
        them with its traceback, so an ERROR at the raising site writes the same fault twice. The site may
        still add its context at DEBUG.
        """
        server_errors = {
            name
            for name, value in vars(core_exceptions).items()
            if isinstance(value, type) and issubclass(value, core_exceptions.DomainError) and value.status_code >= 500
        }

        def raised_name(node: ast.Raise) -> str | None:
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(target, ast.Attribute):
                return target.attr
            return target.id if isinstance(target, ast.Name) else None

        offenders: list[str] = []
        for path in _app_files():
            if "alembic" in path.parts or "migrations" in path.parts:
                continue
            for block in ast.walk(ast.parse(path.read_text())):
                if not isinstance(block, (ast.ExceptHandler, ast.If)):
                    continue
                raises = [node for node in block.body if isinstance(node, ast.Raise) and node.exc is not None]
                if not any(raised_name(node) in server_errors for node in raises):
                    continue
                offenders.extend(
                    f"{path}:{node.value.lineno}"
                    for node in block.body
                    if isinstance(node, ast.Expr)
                    and _is_logger_call(node.value)
                    and node.value.func.attr in {"error", "exception", "critical"}
                )

        assert offenders == [], "Log the context at DEBUG; the boundary logs the failure:\n  " + "\n  ".join(offenders)

    def test_a_loop_logs_its_items_at_debug_and_one_summary_at_info(self):
        """``logger.info`` inside a loop writes one line per item; the item is DEBUG and the summary follows the loop."""

        def info_in_loops(node: ast.AST, in_loop: bool = False):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    yield from info_in_loops(child, False)
                    continue
                if in_loop and _is_logger_call(child) and child.func.attr == "info":
                    yield child.lineno
                yield from info_in_loops(child, in_loop or isinstance(child, (ast.For, ast.AsyncFor, ast.While)))

        offenders = [
            f"{path}:{line}"
            for path in _app_files()
            if not set(path.parts) & set(_INFO_IN_LOOP_EXEMPT_DIRS)
            and path.relative_to(_APP).as_posix() not in _INFO_IN_LOOP
            for line in info_in_loops(ast.parse(path.read_text()))
        ]

        assert offenders == [], "Log the item at DEBUG and one INFO summary after the loop:\n  " + "\n  ".join(
            offenders
        )
