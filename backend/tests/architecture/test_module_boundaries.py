"""Module-boundary conformance, enforced.

The rule from ``docs/developer-guide/module-structure.md`` that import-linter
cannot express. A ``forbidden`` contract rejects an import when *any* source
matches *any* forbidden module, so the wildcard pair
``modules.activities.* -> modules.activities.*.crud`` — the natural way to say
"a sub-package's persistence is private" — also rejects
``activity_laps.service -> activity_laps.crud``, which is the layering the
project requires. There is no way to say "except your own package".

So it is checked here instead: walk the AST, compare each import against the
importer's own sub-package, and consult an explicit allowlist of named seams.
That allowlist is the debt register — every entry is a real cross-package reach
with the reason it still exists, and anything not listed fails.
"""

import ast
import fnmatch
import pathlib
import tomllib

from tests._helpers.module_roles import CONVERTED_MODULES, UNCONVERTED_MODULES
from tests._helpers.module_roles import role_of as _role

#: Modules converted to the structure guide, shared with ``test_logging_rule.py`` (also in ``tests/architecture/``)
#: through ``tests/_helpers/module_roles.py``. Opt-in, and ratcheted by
#: ``TestModuleInventory`` so an unconverted module is visibly outstanding
#: rather than silently exempt.
_CONVERTED = CONVERTED_MODULES

_MODULES_ROOT = pathlib.Path("app/modules")

#: The backend directory, anchored to this file so config lookups do not depend on
#: the working directory the tests are started from.
_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]

_APP_ROOT = pathlib.Path("app")

#: Roles one independently extractable activity package may import from another.
#: Data shapes and event declarations carry no implementation; behaviour crosses
#: the boundary only through ``integration_service``. The remaining names are
#: composition surfaces mounted by the application.
#:
#: Matched by ROLE, not by exact filename, so ``summary_router`` is a router
#: without having to be hand-added here and ``summary_crud`` is private without
#: anyone remembering to say so.
_PUBLIC_WITHIN_MODULE = frozenset(
    {
        "schema",
        "contracts",
        "constants",
        "events",
        "integration_service",
        "dependencies",
        "router",
        "public_router",
        "subscriber_registry",
        "scheduled_jobs",
        "model_registry",
        "contributor_registry",
        "contributors",
    }
)

#: Roles importable from *outside* the owning module. Everything else is
#: module-internal or package-private. ``service`` and ``query`` are deliberately
#: absent: they are the module's own layers, not its published surface.
_PUBLIC_ACROSS_MODULES = _PUBLIC_WITHIN_MODULE | {"computation", "contributors"}

_MIGRATION_SURFACE = "migration_service"

#: ``Session`` methods that run a statement. Only a ``crud``-role file may call
#: them. Transaction control is a separate rule (``_TRANSACTION_CONTROL``): the
#: service layer owns the boundary, so a ``crud`` file may flush but not end one.
_SESSION_EXECUTION = frozenset({"execute", "scalars", "scalar", "query", "add", "add_all", "get", "merge"})

#: ``Session`` methods that end a transaction. ``flush`` is deliberately absent:
#: staging a write so constraint errors and row counts surface is persistence's
#: job; deciding when it becomes durable is not.
_TRANSACTION_CONTROL = frozenset({"commit", "rollback"})

#: ``crud`` files that still end transactions themselves, as
#: ``{path relative to modules/: reason}``. This is the debt register for
#: ``test_crud_does_not_end_transactions``. It is empty: every converted module
#: stages and lets ``service`` commit. A module being converted lists its files
#: here until its writers are stage-only; the test fails on an entry that no
#: longer offends so the list cannot outlive the debt.
_CRUD_TRANSACTION_DEBT: dict[str, str] = {}

#: Cross-sub-package reaches that are part of the design, as
#: ``(importer glob, imported glob): reason``. Globs are module paths relative
#: to the module root (``activity.integration_service``, ``activity_laps.crud``).
_INTRA_MODULE_SEAMS: dict[tuple[str, str], str] = {}

#: Reaches past a module's surface from outside it, as
#: ``(importer module path, imported glob): reason``.
_INBOUND_EXCEPTIONS: dict[tuple[str, str], str] = {}

#: The callables that build a ``ProfileActivityContributor``: the dataclass itself,
#: and the shared factory the plain child collections go through. Both take the
#: export callback as ``export=``, so either is a legitimate place to wire it.
_PROFILE_CONTRIBUTOR_CONSTRUCTORS = frozenset({"ProfileActivityContributor", "child_profile_contributor"})

#: Multi-activity reads that trust their activity ids were owner-scoped before
#: reaching persistence. Their call surface is deliberately narrower than an
#: ordinary package operation because a new caller could otherwise create an
#: indirect object reference vulnerability.
_BULK_ACTIVITY_READS = {
    "get_activities_laps": "activity_laps",
    "get_activities_media": "activity_media",
    "get_activities_sets": "activity_sets",
    "get_activities_streams": "activity_streams",
    "get_activities_workout_steps": "activity_workout_steps",
}


def _module_path(path: pathlib.Path, root: pathlib.Path) -> str:
    """
    Return a file's dotted path relative to its module root.

    Args:
        path: The Python file.
        root: The module root directory.

    Returns:
        The dotted path, e.g. ``activity.crud`` or ``subscriber_registry``.
    """
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _names_a_module(dotted: str) -> bool:
    """
    Return whether a dotted path names a real module or package on disk.

    Args:
        dotted: A fully qualified dotted path rooted at ``app``.

    Returns:
        True when the path resolves to a ``.py`` file or a package directory.
    """
    base = _APP_ROOT.joinpath(*dotted.split("."))
    return base.with_suffix(".py").is_file() or base.is_dir()


def _imported_modules(path: pathlib.Path) -> set[str]:
    """
    Return every fully qualified module this file imports.

    Args:
        path: The Python file to parse.

    Returns:
        The imported dotted module paths, including ``TYPE_CHECKING`` imports.
    """
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # ``from x.y import z`` names either a submodule or a symbol, and the
            # two have to be told apart on disk. Counting dots does not work: in a
            # flat module ``modules.followers.constants`` has the same depth as a
            # sub-packaged module's ``modules.activities.activity``, so every
            # symbol imported from a flat module read as a submodule.
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                found.add(candidate if _names_a_module(candidate) else node.module)
    return found


def _matches(pair: tuple[str, str], rules: dict[tuple[str, str], str]) -> bool:
    """
    Return whether an import pair is covered by an allowlist.

    Args:
        pair: The ``(importer, imported)`` dotted paths.
        rules: The allowlist keyed by ``(importer glob, imported glob)``.

    Returns:
        True when some rule matches both halves of the pair.
    """
    importer, imported = pair
    return any(
        fnmatch.fnmatch(importer, rule_importer) and fnmatch.fnmatch(imported, rule_imported)
        for rule_importer, rule_imported in rules
    )


def _python_files(root: pathlib.Path) -> list[pathlib.Path]:
    """
    Return the Python files under a directory, newest-stable ordered.

    Args:
        root: The directory to walk.

    Returns:
        The sorted list of ``.py`` files, excluding caches.
    """
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _session_names(tree: ast.AST) -> set[str]:
    """Return the names a file binds to a SQLAlchemy ``Session``.

    The convention is ``db``, but a rule keyed on one spelling is exempted by a rename, so
    any parameter annotated ``Session`` (or ``scoped_session``) counts as well. ``session``
    alone is not assumed: a FIT *session* record is a dict with its own ``get``.

    Args:
        tree: The parsed file.

    Returns:
        ``db`` and every annotated parameter name.
    """
    names = {"db"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                annotation = argument.annotation
                if isinstance(annotation, ast.Name | ast.Attribute):
                    label = annotation.id if isinstance(annotation, ast.Name) else annotation.attr
                    if label in {"Session", "scoped_session"}:
                        names.add(argument.arg)
    return names


def _symbol_reference_nodes(tree: ast.AST, symbols: set[str]) -> list[tuple[ast.AST, str]]:
    """Return AST nodes that reference any named symbol.

    Args:
        tree: Syntax tree to inspect.
        symbols: Unqualified symbol names to locate.

    Returns:
        Reference nodes paired with the symbol each one names.
    """
    references: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        candidates: tuple[str | None, ...]
        if isinstance(node, ast.Name):
            candidates = (node.id,)
        elif isinstance(node, ast.Attribute):
            candidates = (node.attr,)
        elif isinstance(node, ast.alias):
            candidates = (node.name.rsplit(".", 1)[-1], node.asname)
        else:
            continue
        references.extend((node, candidate) for candidate in candidates if candidate in symbols)
    return references


#: Layer rules are stated once, by role, and apply to every file whose stem
#: declares that role (``summary_crud`` is a ``crud``, ``pipeline_service`` a
#: ``service``). They replace per-module import-linter denylists, which matched
#: exact module names, so a qualified stem escaped them and a flat module needed
#: its own copy. An allowlist fails closed: a new file is covered the day it is
#: written, and a role that is not named is not trusted.

#: Roles that may import an ORM ``models`` module. ``model_registry`` names its
#: models by string and so imports none.
_ORM_READERS = frozenset({"models", "crud", "serializers", "query"})

#: Persistence-layer roles: they take no HTTP types and ask no other package.
_PERSISTENCE_ROLES = frozenset({"crud", "query", "serializers"})

#: Roles a transport adapter may not reach: it validates, delegates to its
#: service and returns.
_TRANSPORT_FORBIDDEN = frozenset({"crud", "models", "query", "event_publishers"})

#: Roles of another package that persistence may name: data shapes, not
#: behaviour.
_DATA_ROLES = frozenset({"schema", "contracts", "constants"})

#: Roles of another top-level module that a converted module may import: its
#: published surface. ``identity_service`` is ``auth``'s surface under another
#: name (see the guide); no other module may follow it.
_OUTBOUND_ROLES = frozenset({"integration_service", "schema", "contracts", "constants", "events", "dependencies"})
_OUTBOUND_SURFACE_STEMS = frozenset({"identity_service"})

#: Layer-rule exceptions as ``{(importer, imported): reason}``, in dotted paths
#: rooted at ``app``. Every entry is a deliberate seam; anything else fails.
_LAYER_EXCEPTIONS: dict[tuple[str, str], str] = {}

#: Top-level modules that sit below another, as ``{module: modules it may not import}``.
_MUST_NOT_IMPORT: dict[str, tuple[str, ...]] = {
    "followers": ("modules.activities",),
}


def _module_dotted(path: pathlib.Path) -> str:
    """
    Return a file's fully qualified dotted path rooted at ``app``.

    Args:
        path: The Python file.

    Returns:
        The dotted path, e.g. ``modules.activities.activity.crud``.
    """
    return ".".join(path.relative_to(_APP_ROOT).with_suffix("").parts)


def _package_of(dotted: str) -> str:
    """
    Return the package a module path belongs to.

    Args:
        dotted: A dotted path rooted at ``app``.

    Returns:
        ``modules.<namespace>.<package>`` inside a composition namespace
        (``modules.activities.activity``), otherwise ``modules.<module>``.
    """
    parts = dotted.split(".")
    if len(parts) >= 3 and parts[0] == "modules" and (_MODULES_ROOT / parts[1] / parts[2]).is_dir():
        return ".".join(parts[:3])
    return ".".join(parts[:2])


def _layer_imports(*, only_roles: frozenset[str] | None = None) -> list[tuple[pathlib.Path, str, str, str]]:
    """
    Return every ``modules.*`` import made by a converted-module file.

    Args:
        only_roles: Keep only importers whose file role is in this set.

    Returns:
        ``(file, importer dotted path, imported dotted path, importer role)``.
    """
    found: list[tuple[pathlib.Path, str, str, str]] = []
    for module_name in _CONVERTED:
        for path in _python_files(_MODULES_ROOT / module_name):
            role = _role(path.stem)
            if only_roles is not None and role not in only_roles:
                continue
            for target in _imported_modules(path):
                if target.startswith("modules.") and target.count(".") >= 2:
                    found.append((path, _module_dotted(path), target, role))
    return found


def _excepted(importer: str, imported: str) -> bool:
    """
    Return whether an import is a listed layer exception.

    Args:
        importer: The importing module's dotted path.
        imported: The imported module's dotted path.

    Returns:
        True when the pair is in ``_LAYER_EXCEPTIONS``.
    """
    return (importer, imported) in _LAYER_EXCEPTIONS


#: Surface operations that end the caller's transaction, as
#: ``{"<package>.integration_service.<function>": reason}``. A cross-module call
#: must not commit or roll back the caller's unit of work: partial persistence of
#: someone else's operation is how an invariant breaks. The rule is that a
#: surface write **stages** and its caller commits; what is listed here is
#: deliberately a self-contained unit of work, with the reason it has to be.
_SURFACE_UNITS_OF_WORK: dict[str, str] = {
    "activity.integration_service.store_parsed_activity": (
        "Stages the activity, its components and activity.created, and the caller commits. It rolls back "
        "only on failure: a lost race on the dedup key leaves the session unusable until it is rolled "
        "back, and it has to look up the winner before returning it."
    ),
    "activity_ingestion.integration_service.ingest_activity_file": (
        "The background ingestion entry for provider syncs: it commits each activity and rolls back "
        "a failed file so the rest of the batch continues on the same session."
    ),
    "activity_ingestion.integration_service.request_provider_sync": (
        "Creates the refresh job row and publishes its work event in one commit, so the job and the "
        "outbox event are atomic; the caller is a provider's own route with nothing else to commit."
    ),
    "activity_media.integration_service.attach_media_bytes": (
        "A race on the unique media hash leaves the session unusable until it is rolled back, so the "
        "write has to own the rollback before it looks up the winner."
    ),
}

#: Modules whose functions a transaction walk does not enter: they stage or describe, and a
#: commit in one would already fail ``test_crud_does_not_end_transactions``.
_FOLLOW_STOP_ROLES = frozenset({"crud", "query", "serializers", "models", "schema", "contracts", "constants", "events"})


def _ends_a_transaction(function: ast.AST) -> bool:
    """
    Return whether a function body ends or hands over a transaction.

    Args:
        function: A function definition.

    Returns:
        True when it calls ``commit``/``rollback``, passes a ``commit=`` argument,
        or hands a bound ``commit`` to something else.
    """
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _TRANSACTION_CONTROL
        ):
            return True
        if isinstance(node, ast.keyword) and node.arg == "commit":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "commit" and isinstance(node.ctx, ast.Load):
            return True
    return False


def _transaction_ending_surface() -> set[str]:
    """
    Return every converted-module surface function that can end the caller's transaction.

    Follows a call from a surface function through the modules it imports and
    through same-module helpers, so a commit buried in the module's own
    ``service`` or pipeline is found. Persistence modules and data shapes are not
    followed. Calls made through a function object passed as a value are not
    followed; the surface functions that do this are reads.

    Returns:
        ``"<package>.integration_service.<function>"`` names.
    """
    trees: dict[str, ast.Module] = {}

    def load(dotted: str) -> ast.Module | None:
        if dotted not in trees:
            path = _APP_ROOT.joinpath(*dotted.split(".")).with_suffix(".py")
            trees[dotted] = ast.parse(path.read_text()) if path.is_file() else None  # type: ignore[assignment]
        return trees[dotted]

    def aliases(tree: ast.Module) -> dict[str, str]:
        return {
            alias.asname: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.asname and alias.name.startswith("modules.")
        }

    def reaches(dotted: str, name: str, seen: set[tuple[str, str]], depth: int = 0) -> bool:
        tree = load(dotted)
        if tree is None or depth > 8 or (dotted, name) in seen:
            return False
        seen.add((dotted, name))
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)}
        function = functions.get(name)
        if function is None:
            return False
        if _ends_a_transaction(function):
            return True
        bound = aliases(tree)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id in functions:
                if reaches(dotted, callee.id, seen, depth + 1):
                    return True
            elif isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
                target = bound.get(callee.value.id)
                if (
                    target
                    and _role(target.rsplit(".", 1)[-1]) not in _FOLLOW_STOP_ROLES
                    and reaches(target, callee.attr, seen, depth + 1)
                ):
                    return True
        return False

    found: set[str] = set()
    for module_name in _CONVERTED:
        for path in _python_files(_MODULES_ROOT / module_name):
            if path.name != "integration_service.py":
                continue
            dotted = _module_dotted(path)
            tree = load(dotted)
            assert tree is not None
            package = _module_path(path, _MODULES_ROOT / module_name)
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or node.name.startswith("_"):
                    continue
                if reaches(dotted, node.name, set()):
                    # A flat module's surface is the module itself (``followers``).
                    label = package if "." in package else f"{module_name}.{package}"
                    found.add(f"{label}.{node.name}")
    return found


def _names_reached_through(tree: ast.AST, module: str) -> set[str]:
    """
    Return the names a file accesses on one module.

    Resolves how the file bound the module rather than matching a bare
    attribute name, so ``other.thing`` on an unrelated object is not a use of
    ``module.thing``.

    Args:
        tree: The parsed file.
        module: Fully qualified dotted module path, e.g.
            ``modules.activities.activity_laps.integration_service``.

    Returns:
        The attribute names read from the module and the names imported from it.
    """
    package, _, leaf = module.rpartition(".")
    bound: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == module:
                names.update(alias.name for alias in node.names)
            elif node.module == package:
                bound.update(alias.asname or alias.name for alias in node.names if alias.name == leaf)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and ast.unparse(node.value) in bound:
            names.add(node.attr)
    return names


def _package_graph(module_name: str) -> dict[str, set[str]]:
    """
    Return which sub-packages of a module import which others.

    Args:
        module_name: The module directory under ``app/modules``.

    Returns:
        A mapping of sub-package to the sub-packages it imports. Namespace-level
        files are excluded: composing the packages is their job.
    """
    root = _MODULES_ROOT / module_name
    prefix = f"modules.{module_name}."
    graph: dict[str, set[str]] = {}
    for path in _python_files(root):
        importer = _module_path(path, root)
        if "." not in importer:
            continue
        importer_pkg = importer.split(".")[0]
        edges = graph.setdefault(importer_pkg, set())
        for target in _imported_modules(path):
            if not target.startswith(prefix):
                continue
            imported_pkg = target[len(prefix) :].split(".")[0]
            if imported_pkg != importer_pkg and (root / imported_pkg).is_dir():
                edges.add(imported_pkg)
    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """
    Return one import cycle in a package graph, if any exists.

    Args:
        graph: The package-to-packages mapping.

    Returns:
        The cycle as a path that starts and ends on the same package, or None.
    """
    #: 1 = on the current path, 2 = fully explored.
    state: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for following in sorted(graph.get(node, ())):
            if state.get(following, 0) == 0:
                cycle = visit(following)
                if cycle:
                    return cycle
            elif state[following] == 1:
                return [*path[path.index(following) :], following]
        path.pop()
        state[node] = 2
        return None

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


class TestSubPackagePrivacy:
    """A sub-package's persistence and application layers are private to it."""

    def test_siblings_share_only_data_shapes(self):
        """Anything beyond schema/contracts/constants/events needs a named seam."""
        offenders: list[str] = []
        for module_name in _CONVERTED:
            root = _MODULES_ROOT / module_name
            prefix = f"modules.{module_name}."
            for path in _python_files(root):
                importer = _module_path(path, root)
                importer_pkg = importer.split(".")[0] if "." in importer else ""
                for target in _imported_modules(path):
                    if not target.startswith(prefix):
                        continue
                    imported = target[len(prefix) :]
                    if "." not in imported:
                        continue
                    imported_pkg, imported_stem = imported.rsplit(".", 1)
                    if imported_pkg == importer_pkg:
                        continue
                    if _role(imported_stem) in _PUBLIC_WITHIN_MODULE:
                        continue
                    if _matches((importer, imported), _INTRA_MODULE_SEAMS):
                        continue
                    offenders.append(f"{module_name}: {importer} -> {imported}")
        assert not offenders, (
            "Cross-sub-package reach into a private module. Either use the "
            "sibling's published surface, or add the seam to _INTRA_MODULE_SEAMS "
            "with the reason it exists:\n  " + "\n  ".join(sorted(offenders))
        )

    def test_package_inits_export_nothing(self):
        """A re-export facade would hand out ORM models under a package path."""
        offenders: list[str] = []
        for module_name in _CONVERTED:
            root = _MODULES_ROOT / module_name
            for path in root.rglob("__init__.py"):
                if "__pycache__" in path.parts:
                    continue
                body = ast.parse(path.read_text()).body
                statements = [n for n in body if not isinstance(n, ast.Expr)]
                if statements:
                    offenders.append(str(path))
        assert not offenders, "__init__.py must hold a docstring and nothing else:\n  " + "\n  ".join(sorted(offenders))

    def test_only_crud_executes_against_the_session(self):
        """A file that runs statements is persistence, whatever it is called.

        The rules match on the role a filename declares, so a persistence module
        under some other name inherits none of them. ``summary_query`` executed
        every activity-summary aggregation for exactly that reason: no
        ``modules.activities.*.crud`` contract saw it, and the logging rule
        classified it as a session-free ``query``. Naming is the contract, so it
        is checked rather than trusted.

        Transaction control is a separate rule
        (``test_crud_does_not_end_transactions``).
        """
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if _role(path.stem) == "crud":
                    continue
                tree = ast.parse(path.read_text())
                sessions = _session_names(tree)
                executed = sorted(
                    {
                        f"{node.func.value.id}.{node.func.attr}"
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in _SESSION_EXECUTION
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id in sessions
                    }
                )
                if executed:
                    offenders.append(f"{path} (role={_role(path.stem)}): {', '.join(executed)}")
        assert not offenders, (
            "Only a crud-role file may execute against the session. Move the "
            "query into the package's crud, or rename the file so its role is "
            "the one it actually plays:\n  " + "\n  ".join(sorted(offenders))
        )

    def test_a_surface_does_not_publish_events(self):
        """An ``integration_service`` is a face, not a layer: it calls its own ``service`` to publish.

        A surface that published would own the commit that has to be atomic with the event, leaving
        two write-orchestration layers. Stated for every converted module, so a flat module such as
        ``followers`` is held to it as much as an activities package.
        """
        offenders = sorted(
            {
                f"{importer} -> {imported}"
                for _, importer, imported, _ in _layer_imports(only_roles=frozenset({"integration_service"}))
                if _role(imported.rsplit(".", 1)[-1]) == "event_publishers"
            }
        )

        assert offenders == [], "A surface calls its own service, which publishes:\n  " + "\n  ".join(offenders)

    def test_only_transaction_owners_end_transactions(self):
        """Stating the rule as an allowlist: a file's name cannot exempt it.

        ``test_crud_does_not_end_transactions`` forbids the offence in one role,
        so a file whose name declares no role (``dispatch.py`` once committed
        unnoticed) escaped it. The owners of a unit of work are services,
        durable-job and subscriber entry points, and the ``migration_service``
        adapters; any other file asks one of them.
        """
        owners = {"service", "migration_service", "subscribers", "scheduled_jobs"}
        offenders = [
            f"{path.relative_to(_MODULES_ROOT).as_posix()}: role '{_role(path.stem)}'"
            for module_name in _CONVERTED
            for path in _python_files(_MODULES_ROOT / module_name)
            if _role(path.stem) not in owners
            and any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _TRANSACTION_CONTROL
                for node in ast.walk(ast.parse(path.read_text()))
            )
        ]
        assert not offenders, (
            "Only a service, subscriber, scheduled job or migration_service may end a transaction. "
            "Name the file for the role it plays, or move the commit into a service:\n  " + "\n  ".join(offenders)
        )

    def test_crud_does_not_end_transactions(self):
        """Persistence stages a write; the service decides when it is durable.

        Only the layer that knows the whole unit of work can commit it: a service
        stages a row, publishes the event and commits so the two are atomic. A
        ``crud`` that commits itself makes that atomicity depend on the caller
        remembering to opt out, and it is the default branch that nobody
        exercises. ``flush`` is allowed (it surfaces constraint errors and row
        counts); ``commit`` and ``rollback`` are not. Rolling back belongs to the
        transaction owner, which is the service or ``core.database.get_db``.

        ``_CRUD_TRANSACTION_DEBT`` records the files that still do. It shrinks;
        a stale entry fails, so it cannot outlive the debt.
        """
        offenders: list[str] = []
        stale: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if _role(path.stem) != "crud":
                    continue
                ended = sorted(
                    {
                        node.func.attr
                        for node in ast.walk(ast.parse(path.read_text()))
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in _TRANSACTION_CONTROL
                        and isinstance(node.func.value, ast.Name)
                    }
                )
                relative = path.relative_to(_MODULES_ROOT).as_posix()
                if ended and relative not in _CRUD_TRANSACTION_DEBT:
                    offenders.append(f"{relative}: .{', .'.join(ended)}()")
                if not ended and relative in _CRUD_TRANSACTION_DEBT:
                    stale.append(relative)
        assert not offenders, (
            "A crud-role file may flush but not commit or roll back. Stage the "
            "write and let the service own the transaction:\n  " + "\n  ".join(sorted(offenders))
        )
        assert not stale, (
            "These files no longer end transactions; remove them from "
            "_CRUD_TRANSACTION_DEBT:\n  " + "\n  ".join(sorted(stale))
        )

    def test_a_file_plays_the_role_its_content_declares(self):
        """A router or an ORM model cannot hide under a helper name.

        Roles are read off filenames, so a file under a name the vocabulary does
        not know is package-private and inherits none of the router or ORM rules.
        ``test_only_crud_executes_against_the_session`` holds the persistence
        half; this holds the other two. The vocabulary is deliberately not
        closed — ``pipeline.py``, ``render.py`` and ``signing.py`` are legitimate
        private helpers — so the check is that a file's *content* agrees with
        its name, not that its name is on a list.
        """
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                role = _role(path.stem)
                nodes = list(ast.walk(ast.parse(path.read_text())))
                declares_router = any(
                    isinstance(node, ast.Call)
                    and getattr(node.func, "attr", getattr(node.func, "id", None)) == "APIRouter"
                    for node in nodes
                )
                declares_model = any(
                    isinstance(node, ast.ClassDef)
                    and any(isinstance(base, ast.Name) and base.id == "Base" for base in node.bases)
                    for node in nodes
                )
                if declares_router and role not in {"router", "public_router"}:
                    offenders.append(f"{path} (role={role}): constructs an APIRouter")
                if declares_model and role != "models":
                    offenders.append(f"{path} (role={role}): declares an ORM model")
        assert not offenders, (
            "A file's role is its filename, so the filename has to say what the "
            "file is. Rename it into the vocabulary in "
            "tests/_helpers/module_roles.py:\n  " + "\n  ".join(sorted(offenders))
        )


class TestModuleInventory:
    """Every top-level module is either converted or explicitly outstanding."""

    def test_every_top_level_module_is_classified(self):
        """A module in neither list would start life outside every rule.

        The conformance tests are opt-in (``CONVERTED_MODULES``), which is the
        right default while modules convert one PR at a time, and the wrong one
        for a module nobody has thought about yet: it is exempt from all of them
        without a single line saying so. Naming the outstanding modules makes
        "convert it" and "consciously leave it" the only two options for a new
        one. Converting a module is moving its name between the two lists in
        ``tests/_helpers/module_roles.py``.
        """
        on_disk = {
            path.name for path in _MODULES_ROOT.iterdir() if path.is_dir() and not path.name.startswith(("_", "."))
        }
        declared = set(CONVERTED_MODULES) | set(UNCONVERTED_MODULES)
        unclassified = sorted(on_disk - declared)
        stale = sorted(declared - on_disk)
        assert not unclassified, (
            "Top-level module in neither CONVERTED_MODULES nor UNCONVERTED_MODULES "
            "(tests/_helpers/module_roles.py). Convert it to the structure guide, "
            "or list it as outstanding:\n  " + "\n  ".join(unclassified)
        )
        assert not stale, "Listed in module_roles.py but not on disk:\n  " + "\n  ".join(stale)
        assert not set(CONVERTED_MODULES) & set(UNCONVERTED_MODULES), (
            "A module cannot be both converted and outstanding"
        )


class TestLayerRules:
    """Layer rules by role, so a qualified filename cannot escape them."""

    def test_only_persistence_reaches_orm_models(self):
        """An ORM row never leaves ``crud`` and its edge helpers.

        Application layers go through ``crud``, which returns schemas and DTOs,
        so a service or router cannot hold a live ORM instance and mutate it
        outside the transaction that owns it.
        """
        offenders = sorted(
            f"{importer} -> {imported}"
            for _path, importer, imported, role in _layer_imports()
            if _role(imported.rsplit(".", 1)[-1]) == "models"
            and role not in _ORM_READERS
            and not _excepted(importer, imported)
        )
        assert not offenders, (
            "Only models/crud/serializers/query may import an ORM models module. "
            "Read it through the owning crud:\n  " + "\n  ".join(offenders)
        )

    def test_transport_delegates_to_its_service(self):
        """A router validates, calls its service and returns.

        No persistence, no ORM and no event publishing in the transport layer:
        the access decision and the transaction live in ``service``, so a handler
        cannot quietly skip them.
        """
        offenders = sorted(
            f"{importer} -> {imported}"
            for _path, importer, imported, _role_ in _layer_imports(only_roles=frozenset({"router", "public_router"}))
            if _role(imported.rsplit(".", 1)[-1]) in _TRANSPORT_FORBIDDEN and not _excepted(importer, imported)
        )
        assert not offenders, "A router must delegate to its service:\n  " + "\n  ".join(offenders)

    def test_persistence_raises_domain_errors_not_http_ones(self):
        """Persistence describes what went wrong, not which status to send.

        The durable-job worker serves no HTTP, so a persistence module that
        imports FastAPI drags a transport into a place with none.
        """
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if _role(path.stem) not in _PERSISTENCE_ROLES | {"models"}:
                    continue
                offenders.extend(
                    f"{_module_dotted(path)} -> {target}"
                    for target in _imported_modules(path)
                    if target == "fastapi" or target.startswith("fastapi.")
                )
        assert not offenders, "Persistence raises core.exceptions, not HTTP errors:\n  " + "\n  ".join(
            sorted(offenders)
        )

    def test_persistence_asks_no_other_package(self):
        """A query that must ask another bounded context first is a service decision.

        The value is resolved by the layer above and passed in, so the query can
        be reasoned about, tested and reused with no other package present. Data
        shapes (schema, contracts, constants) stay allowed: a shape is not a
        question.
        """
        offenders = sorted(
            f"{importer} -> {imported}"
            for _path, importer, imported, _role_ in _layer_imports(only_roles=_PERSISTENCE_ROLES)
            if _package_of(imported) != _package_of(importer)
            and _role(imported.rsplit(".", 1)[-1]) not in _DATA_ROLES
            and not _excepted(importer, imported)
        )
        assert not offenders, (
            "Persistence may import another package only for its data shapes. Resolve "
            "the value in service and pass it in, or add a reasoned seam to "
            "_LAYER_EXCEPTIONS:\n  " + "\n  ".join(offenders)
        )

    def test_outbound_reach_uses_a_published_surface(self):
        """A converted module reaches another top-level module only through its surface.

        Stated as an allowlist, so a file added to an unconverted module (a new
        ``utils.py``) is not importable until someone publishes it, instead of
        being importable until someone remembers to deny it.
        """
        offenders: list[str] = []
        for _path, importer, imported, _importer_role in _layer_imports():
            if imported.split(".")[1] == importer.split(".")[1]:
                continue
            stem = imported.rsplit(".", 1)[-1]
            if _role(stem) in _OUTBOUND_ROLES or stem in _OUTBOUND_SURFACE_STEMS:
                continue
            if not _excepted(importer, imported):
                offenders.append(f"{importer} -> {imported}")
        assert not offenders, (
            "Reach into another module's internals. Add the operation to its integration_service:\n  "
            + "\n  ".join(sorted(offenders))
        )

    def test_lower_modules_do_not_import_the_modules_above_them(self):
        """Followers sits below activities, which consumes it, never the reverse."""
        offenders = sorted(
            f"{importer} -> {imported}"
            for _path, importer, imported, _role_ in _layer_imports()
            if any(
                importer.split(".")[1] == module and imported.startswith(forbidden)
                for module, forbidden_modules in _MUST_NOT_IMPORT.items()
                for forbidden in forbidden_modules
            )
        )
        assert not offenders, "Dependency direction is one-way:\n  " + "\n  ".join(offenders)

    def test_layer_exceptions_are_still_used(self):
        """An exception that no import needs any more is removed, not left to rot."""
        used = {(importer, imported) for _path, importer, imported, _role_ in _layer_imports()}
        stale = sorted(f"{a} -> {b}" for a, b in _LAYER_EXCEPTIONS if (a, b) not in used)
        assert not stale, "Remove from _LAYER_EXCEPTIONS:\n  " + "\n  ".join(stale)


class TestSurfaceTransactions:
    """A cross-module call must not end the caller's transaction."""

    def test_surface_operations_stage_unless_they_are_a_listed_unit_of_work(self):
        """Stage-and-let-the-caller-commit is the default for a surface write.

        A caller that composes two surface calls needs them atomic, and a
        module that can commit another module's session can persist half of an
        operation it does not own. The few operations that must own the commit
        (they publish an event that has to be atomic with the change, or own a
        rollback) are listed with the reason.
        """
        ending = _transaction_ending_surface()
        unexpected = sorted(ending - set(_SURFACE_UNITS_OF_WORK))
        assert not unexpected, (
            "These surface operations end the caller's transaction. Stage through crud "
            "and let the caller commit, or list them in _SURFACE_UNITS_OF_WORK with the "
            "reason they must own it:\n  " + "\n  ".join(unexpected)
        )

    def test_listed_units_of_work_still_end_a_transaction(self):
        """An entry that no longer commits is removed, so the list cannot rot."""
        stale = sorted(set(_SURFACE_UNITS_OF_WORK) - _transaction_ending_surface())
        assert not stale, "Remove from _SURFACE_UNITS_OF_WORK:\n  " + "\n  ".join(stale)


class TestDocstringScope:
    """The docstring lint applies exactly to the converted modules."""

    def test_unconverted_modules_are_the_ones_exempt_from_the_docstring_lint(self):
        """Converting a module is removing it from the ruff ``D`` ignore list.

        ``pyproject.toml`` exempts a module from the pydocstyle rules by name, so
        the exemption list and ``UNCONVERTED_MODULES`` are one fact stated twice.
        This test is what keeps them one: a module cannot be converted and stay
        exempt, nor be unconverted and silently linted.
        """
        config = tomllib.loads((_BACKEND_ROOT / "pyproject.toml").read_text())
        ignores = config["tool"]["ruff"]["lint"]["per-file-ignores"]
        exempt = {
            pattern.split("/")[2]
            for pattern, rules in ignores.items()
            if pattern.startswith("app/modules/") and "D" in rules
        }
        assert exempt == set(UNCONVERTED_MODULES), (
            "pyproject.toml per-file-ignores for rule D must list exactly the unconverted "
            f"modules; exempt={sorted(exempt)}, unconverted={sorted(UNCONVERTED_MODULES)}"
        )


class TestProviderResolution:
    """A platform provider is resolved at an entry point and passed down."""

    #: Roles that are entry points: something external (HTTP, the bus, the
    #: scheduler, a peer module) calls them with nothing to carry a provider.
    _ENTRY_ROLES = frozenset({"router", "public_router", "subscribers", "integration_service", "scheduled_jobs"})

    def test_services_and_helpers_receive_their_providers(self):
        """``get_active_platform()`` is a service locator, so it stays at the edge.

        A function that reaches for the process-wide platform has a dependency
        its signature does not show: it cannot be tested without patching the
        runtime, and it cannot be lifted out of this application without
        dragging the runtime with it. Entry points resolve the provider once and
        hand it down as an argument; routers declare it with
        ``Depends(core.dependencies.get_storage)`` so a test overrides it.
        """
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if _role(path.stem) in self._ENTRY_ROLES:
                    continue
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, ast.Attribute) and node.attr in {"get_active_platform", "get_state"}:
                        offenders.append(f"{path}:{node.lineno}")
        assert not offenders, (
            "Provider resolved below an entry point. Take the provider as an "
            "argument and resolve it in the router (Depends), subscriber, job or "
            "integration_service that calls you:\n  " + "\n  ".join(sorted(offenders))
        )


class TestPackageIndependence:
    """A package is the unit of extraction, so the graph between them is a DAG."""

    def test_sub_packages_do_not_import_each_other_in_a_cycle(self):
        """Two packages that import each other are one package pretending to be two.

        Every rule above is about *what* one package may reach for in another;
        none of them notices when the reaching goes both ways. ``activity`` and
        ``activity_thumbnail`` each used the other's ``integration_service`` —
        legal on both counts, and still a pair that could not be built, tested or
        lifted out separately: serializing an activity needed the thumbnail
        package to address the blob, and the thumbnail package needed the
        activity row it derives from.

        Direction is the fix, not politeness about surfaces. A derived subsystem
        depends on what it derives from; when the root needs something back, it
        states the seam (``contributor_registry``) and composition installs the
        answer.
        """
        offenders: list[str] = []
        for module_name in _CONVERTED:
            cycle = _find_cycle(_package_graph(module_name))
            if cycle:
                offenders.append(f"{module_name}: {' -> '.join(cycle)}")
        assert not offenders, (
            "Import cycle between packages that are supposed to be independently "
            "extractable. Invert the edge that points from the depended-on "
            "package back to its dependant:\n  " + "\n  ".join(offenders)
        )


class TestOwnerScopedBulkReads:
    """Bulk reads without access checks stay behind owner-scoped profile export."""

    def test_bulk_reads_are_referenced_only_inside_their_own_package(self):
        """Reject callers outside each bulk read's CRUD and integration surface."""
        offenders: list[str] = []
        symbols = set(_BULK_ACTIVITY_READS)
        for path in _python_files(_APP_ROOT):
            tree = ast.parse(path.read_text())
            for node, symbol in _symbol_reference_nodes(tree, symbols):
                package = _BULK_ACTIVITY_READS[symbol]
                package_root = _MODULES_ROOT / "activities" / package
                if path in {package_root / "crud.py", package_root / "integration_service.py"}:
                    continue
                offenders.append(f"{path}:{node.lineno}: references {symbol}")
        assert not offenders, (
            "A multi-activity bulk read that trusts pre-scoped ids gained a "
            "caller outside its package. A new caller is a latent IDOR; route "
            "profile export through the owning package's contributor:\n  " + "\n  ".join(sorted(offenders))
        )

    def test_bulk_read_helpers_are_private_profile_exports(self):
        """Keep each integration wrapper private and wired only as ``export``."""
        offenders: list[str] = []
        for bulk_read, package in _BULK_ACTIVITY_READS.items():
            integration_path = _MODULES_ROOT / "activities" / package / "integration_service.py"
            integration_tree = ast.parse(integration_path.read_text())
            reader_functions = [
                node
                for node in integration_tree.body
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and _symbol_reference_nodes(node, {bulk_read})
            ]
            if len(reader_functions) != 1:
                offenders.append(
                    f"{integration_path}: expected one wrapper around {bulk_read}, found {len(reader_functions)}"
                )
                continue

            helper = reader_functions[0]
            if not helper.name.startswith("_"):
                offenders.append(f"{integration_path}:{helper.lineno}: {helper.name} must be private")

            permitted_reference_ids: set[int] = set()
            for call in (node for node in ast.walk(integration_tree) if isinstance(node, ast.Call)):
                if isinstance(call.func, ast.Attribute):
                    constructor = call.func.attr
                elif isinstance(call.func, ast.Name):
                    constructor = call.func.id
                else:
                    constructor = None
                if constructor not in _PROFILE_CONTRIBUTOR_CONSTRUCTORS:
                    continue
                for keyword in call.keywords:
                    if (
                        keyword.arg == "export"
                        and isinstance(keyword.value, ast.Name)
                        and keyword.value.id == helper.name
                    ):
                        permitted_reference_ids.add(id(keyword.value))

            references: list[tuple[pathlib.Path, ast.AST]] = []
            for path in _python_files(_APP_ROOT):
                tree = integration_tree if path == integration_path else ast.parse(path.read_text())
                references.extend(
                    (path, node)
                    for node, _symbol in _symbol_reference_nodes(tree, {helper.name})
                    if id(node) not in permitted_reference_ids
                )
            if len(permitted_reference_ids) != 1:
                offenders.append(
                    f"{integration_path}:{helper.lineno}: {helper.name} must be the export callback of exactly one "
                    "ProfileActivityContributor"
                )
            offenders.extend(
                f"{path}:{node.lineno}: references {helper.name} outside its profile export wiring"
                for path, node in references
            )

        assert not offenders, (
            "A wrapper around an owner-scoped bulk read escaped the private "
            "profile export seam:\n  " + "\n  ".join(sorted(offenders))
        )


class TestModuleSurface:
    """Other modules consume a module only through its published surface."""

    def test_the_surface_holds_only_operations_with_callers(self):
        """A published function nobody calls is API surface with no user.

        ``integration_service`` is the one file other modules may depend on, so
        every name in it is a promise. The child packages had grown six public
        functions each where two were reached from outside: the contributor
        plumbing (``store_laps``, ``restore_profile_records``,
        ``list_laps_for_activities``) was published alongside the contributor
        factory that was the actual surface, so "what may I depend on?" answered
        with three times more than the module meant.

        A caller is a file **outside the package** that reaches the function
        through the module it imported: ``alias.name`` for ``import x as alias``,
        or ``name`` for ``from x import name``. A same-named attribute on some
        other object does not count, and neither does the package calling its own
        surface, which is a function that belongs in the package, not on its
        face. A new operation lands here together with the caller that needed it,
        or it stays private until then.
        """
        trees = {path: ast.parse(path.read_text()) for path in _python_files(_APP_ROOT)}
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if path.name != "integration_service.py":
                    continue
                dotted = ".".join(path.relative_to(_APP_ROOT).with_suffix("").parts)
                called = {
                    name
                    for other, tree in trees.items()
                    if path.parent not in other.parents
                    for name in _names_reached_through(tree, dotted)
                }
                for node in trees[path].body:
                    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                        continue
                    if node.name.startswith("_") or node.name in called:
                        continue
                    offenders.append(f"{_module_path(path, _APP_ROOT)}.{node.name}")
        assert not offenders, (
            "Published on an integration surface with no caller outside its package. "
            "Make it private until something needs it:\n  " + "\n  ".join(sorted(offenders))
        )

    def test_outsiders_use_the_published_surface(self):
        """A reach past the surface needs an entry in _INBOUND_EXCEPTIONS."""
        offenders: list[str] = []
        app_root = pathlib.Path("app")
        for module_name in _CONVERTED:
            module_root = _MODULES_ROOT / module_name
            prefix = f"modules.{module_name}."
            for path in _python_files(app_root):
                if module_root in path.parents or path == module_root:
                    continue
                importer = _module_path(path, app_root)
                for target in _imported_modules(path):
                    if not target.startswith(prefix):
                        continue
                    imported = target[len(prefix) :]
                    # A dotless target is either a sub-package (importing the bare
                    # package yields nothing, so it is not a reach) or a
                    # module-level file — which IS the whole surface of a flat
                    # module like followers, so it has to be checked.
                    if "." not in imported and (module_root / imported).is_dir():
                        continue
                    if _role(imported.rsplit(".", 1)[-1]) in _PUBLIC_ACROSS_MODULES:
                        continue
                    if importer.startswith("migrations.") and _role(imported.rsplit(".", 1)[-1]) == _MIGRATION_SURFACE:
                        continue
                    if _matches((importer, imported), _INBOUND_EXCEPTIONS):
                        continue
                    offenders.append(f"{importer} -> {module_name}.{imported}")
        assert not offenders, (
            "Reach past a module's published surface. Either add the operation "
            "to the module's integration_service, or record the exception in "
            "_INBOUND_EXCEPTIONS:\n  " + "\n  ".join(sorted(offenders))
        )


#: Roles that may read application settings (``core.config``). Everything else is a
#: pure layer: a parser, renderer, query, serializer or contract that needs a value
#: takes it as a parameter, so it can be tested and reused with no settings present.
_MAY_READ_CONFIGURATION = frozenset(
    {
        "service",
        "router",
        "public_router",
        "dependencies",
        "subscribers",
        "scheduled_jobs",
        "integration_service",
        "migration_service",
    }
)


class TestConfigurationReads:
    """Settings are read where the application decides, never inside a pure layer."""

    def test_only_application_layers_read_configuration(self):
        """``core.config`` is a declared dependency of the application layers.

        Providers are passed down because a dependency has to be visible in a signature;
        configuration is the same kind of dependency. A parser that fell back to
        ``settings.TZ`` or a contract that computed a directory from settings had a hidden
        input that tests had to patch and a library extraction would have to drag along.
        """
        offenders = sorted(
            f"{_module_dotted(path)} ({_role(path.stem)})"
            for module_name in _CONVERTED
            for path in _python_files(_MODULES_ROOT / module_name)
            if _role(path.stem) not in _MAY_READ_CONFIGURATION
            and any(target == "core.config" or target.startswith("core.config.") for target in _imported_modules(path))
        )

        assert not offenders, (
            "A pure layer imports core.config. Take the value as a parameter and read it in a "
            "service, router, subscriber or job:\n  " + "\n  ".join(offenders)
        )


class TestReadModelsAreStoredRows:
    """A ``<Thing>Read`` is what the server returns, so its ``id`` is never optional."""

    def test_read_models_require_their_id(self):
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if _role(path.stem) not in {"schema", "contracts"}:
                    continue
                for node in ast.walk(ast.parse(path.read_text())):
                    if not (isinstance(node, ast.ClassDef) and node.name.endswith("Read")):
                        continue
                    for statement in node.body:
                        if (
                            isinstance(statement, ast.AnnAssign)
                            and isinstance(statement.target, ast.Name)
                            and statement.target.id == "id"
                            and (
                                (statement.value is not None and _is_none_default(statement.value))
                                or "None" in ast.unparse(statement.annotation)
                            )
                        ):
                            offenders.append(f"{_module_dotted(path)}::{node.name}")

        assert not offenders, (
            "A Read model has an optional id, which usually means it is also used as a write input. "
            "Give the input its own <Thing>Create in contracts.py:\n  " + "\n  ".join(sorted(offenders))
        )


def _is_none_default(value: ast.expr) -> bool:
    """Return whether an assignment's value is a ``None`` default.

    Args:
        value: The right-hand side of an annotated assignment.

    Returns:
        True for ``= None`` and for ``Field(default=None, ...)``.
    """
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    if isinstance(value, ast.Call):
        return any(
            keyword.arg == "default" and isinstance(keyword.value, ast.Constant) and keyword.value.value is None
            for keyword in value.keywords
        )
    return False
