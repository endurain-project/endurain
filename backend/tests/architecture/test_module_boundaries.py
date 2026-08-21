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
import re

from tests._helpers.module_roles import role_of as _role

#: Modules converted to the structure guide. Opt-in, like ``_CONVERTED`` in
#: ``test_logging_rule.py``: an unconverted module is visibly outstanding rather
#: than silently exempt.
_CONVERTED = ("activities", "followers")

_MODULES_ROOT = pathlib.Path("app/modules")

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
    }
)

#: Roles importable from *outside* the owning module. Everything else is
#: module-internal or package-private. ``service`` and ``query`` are deliberately
#: absent: they are the module's own layers, not its published surface.
_PUBLIC_ACROSS_MODULES = (_PUBLIC_WITHIN_MODULE - {"service", "query"}) | frozenset(
    {
        "integration_service",
        "subscriber_registry",
        "scheduled_jobs",
        "computation",
        "dependencies",
        "router",
        "public_router",
    }
)

_MIGRATION_SURFACE = "migration_service"

#: ``Session`` methods that run a statement. Only a ``crud``-role file may call
#: them; transaction control (``commit`` / ``flush`` / ``rollback``) is excluded
#: because the service layer owns the boundary.
_SESSION_EXECUTION = frozenset({"execute", "scalars", "scalar", "query", "add", "add_all", "get", "merge"})

#: Cross-sub-package reaches that are part of the design, as
#: ``(importer glob, imported glob): reason``. Globs are module paths relative
#: to the module root (``activity.integration_service``, ``activity_laps.crud``).
_INTRA_MODULE_SEAMS: dict[tuple[str, str], str] = {}

#: Reaches past a module's surface from outside it, as
#: ``(importer module path, imported glob): reason``.
_INBOUND_EXCEPTIONS: dict[tuple[str, str], str] = {}


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

        Transaction control is deliberately not listed: ``commit`` / ``flush`` /
        ``rollback`` belong to the service layer that owns the boundary.
        """
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if _role(path.stem) == "crud":
                    continue
                executed = sorted(
                    {
                        node.func.attr
                        for node in ast.walk(ast.parse(path.read_text()))
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in _SESSION_EXECUTION
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "db"
                    }
                )
                if executed:
                    offenders.append(f"{path} (role={_role(path.stem)}): db.{', db.'.join(executed)}")
        assert not offenders, (
            "Only a crud-role file may execute against the session. Move the "
            "query into the package's crud, or rename the file so its role is "
            "the one it actually plays:\n  " + "\n  ".join(sorted(offenders))
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

        Callers are matched by attribute access, which is how this codebase
        imports (``import x.y as z`` then ``z.f()``). A new operation lands here
        together with the caller that needed it, or it stays private until then.
        """
        app_texts = {path: path.read_text() for path in _python_files(_APP_ROOT)}
        offenders: list[str] = []
        for module_name in _CONVERTED:
            for path in _python_files(_MODULES_ROOT / module_name):
                if path.name != "integration_service.py":
                    continue
                for node in ast.parse(app_texts[path]).body:
                    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                        continue
                    if node.name.startswith("_"):
                        continue
                    used = re.compile(rf"\.{re.escape(node.name)}\b")
                    if not any(used.search(text) for other, text in app_texts.items() if other != path):
                        offenders.append(f"{_module_path(path, _APP_ROOT)}.{node.name}")
        assert not offenders, (
            "Published on an integration surface with no caller. Make it private "
            "until something needs it:\n  " + "\n  ".join(sorted(offenders))
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
