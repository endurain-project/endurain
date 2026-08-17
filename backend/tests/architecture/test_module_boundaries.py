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

#: Modules converted to the structure guide. Opt-in, like ``_CONVERTED`` in
#: ``test_logging_rule.py``: an unconverted module is visibly outstanding rather
#: than silently exempt.
_CONVERTED = ("activities",)

_MODULES_ROOT = pathlib.Path("app/modules")

#: File stems a sibling sub-package may import: data shapes and event
#: declarations, which carry no behaviour and no persistence.
_PUBLIC_WITHIN_MODULE = frozenset({"schema", "contracts", "constants", "events"})

#: File stems importable from *outside* the owning module. Everything else is
#: module-internal or package-private.
_PUBLIC_ACROSS_MODULES = _PUBLIC_WITHIN_MODULE | frozenset(
    {
        "integration_service",
        "subscriber_registry",
        "dependencies",
        "router",
        "public_router",
    }
)

#: Cross-sub-package reaches that are part of the design, as
#: ``(importer glob, imported glob): reason``. Globs are module paths relative
#: to the module root (``activity.integration_service``, ``activity_laps.crud``).
_INTRA_MODULE_SEAMS: dict[tuple[str, str], str] = {
    (
        "activity.integration_service",
        "*.crud",
    ): "The module's outward surface. An activity spans its child collections, so presenting one face outward means reading them.",
    (
        "activity.ingestion_service",
        "*.crud",
    ): "The module's inward write seam: one parsed activity is stored as a root row plus its children, in one transaction.",
    (
        "*.models",
        "*.models",
    ): "SQLAlchemy relationships share one registry, so a child table must name its parent. A foreign key, not a behavioural reach.",
    (
        "*.crud",
        "activity.models",
    ): "Child rows are keyed by activity id and their access filter joins the parent table. Debt: the join belongs behind an activity-owned projection.",
    (
        "*.service",
        "activity.child_access",
    ): "The one shared gate deciding whether a caller may read an activity's children — deliberately not duplicated per child.",
    (
        "activity_ingestion.pipeline",
        "*",
    ): "The ingestion orchestrator. Its job is to drive parse -> enrich -> store -> retain across the packages that own each step.",
    (
        "activity.serializers",
        "activity_thumbnail.signing",
    ): "Serializing an activity mints its thumbnail capability URL. Addressing only — the renderer is not pulled into the read path.",
    (
        "subscriber_registry",
        "*subscribers",
    ): "The module's event-wiring surface; collecting the handlers is the whole point of the file.",
    (
        "subscriber_registry",
        "activity_thumbnail.service",
    ): "Declares the thumbnail subscriber's reconciliation backfill alongside the subscriber it nets.",
    # --- Debt: derived subsystems reading another package's persistence -----
    (
        "activity_thumbnail.*",
        "activity.crud",
    ): "DEBT: needs a root-row projection; none is published, so it reads the CRUD.",
    (
        "activity_thumbnail.*",
        "activity_streams.crud",
    ): "DEBT: needs the GPS stream to render; no read projection is published.",
    (
        "activity_geocoding.service",
        "activity.crud",
    ): "DEBT: needs a root-row projection to write the resolved location back.",
    (
        "activity_geocoding.service",
        "activity_streams.crud",
    ): "DEBT: needs the first GPS waypoint; no read projection is published.",
    (
        "activity_media.service",
        "activity.crud",
    ): "DEBT: needs an ownership check on the parent row; no projection is published.",
    (
        "activity_summaries.crud",
        "activity.models",
    ): "DEBT: a second package aggregating over a table it does not own.",
    (
        "activity_summaries.crud",
        "activity.query",
    ): "DEBT: a second package aggregating over a table it does not own.",
}

#: Reaches past a module's surface from outside it, as
#: ``(importer module path, imported glob): reason``.
_INBOUND_EXCEPTIONS: dict[tuple[str, str], str] = {
    (
        "migrations.*",
        "*",
    ): "Data migrations are pinned to the schema of their era; routing them through a surface that evolves would break them.",
    (
        "core.scheduler",
        "activity_geocoding.subscribers",
    ): "DEBT: platform -> domain inversion. The scheduler enumerates each module's recurring jobs instead of collecting them.",
    (
        "core.scheduler",
        "activity_streams.subscribers",
    ): "DEBT: platform -> domain inversion. The scheduler enumerates each module's recurring jobs instead of collecting them.",
    (
        "core.scheduler",
        "activity_thumbnail.service",
    ): "DEBT: platform -> domain inversion. The scheduler enumerates each module's recurring jobs instead of collecting them.",
    (
        "core.scheduler",
        "activity_ingestion.ingestion_jobs",
    ): "DEBT: platform -> domain inversion. The scheduler enumerates each module's recurring jobs instead of collecting them.",
    (
        "main",
        "activity_ingestion.background",
    ): "Entrypoint wiring: the background executor is started and drained with the app lifespan.",
    (
        "modules.strava.*",
        "activity.ingestion_service",
    ): "The provider store seam, the counterpart of integration_service for writes.",
    (
        "modules.strava.*",
        "activity_ingestion.*",
    ): "DEBT: provider cycle. Providers drive bulk import while ingestion imports them back.",
    (
        "modules.garmin.*",
        "activity_ingestion.*",
    ): "DEBT: provider cycle. Providers drive bulk import while ingestion imports them back.",
    (
        "modules.strava.*",
        "activity_file_import.computation",
    ): "DEBT: provider payload maths reusing the parsers' pure helpers; belongs in a shared computation surface.",
    (
        "modules.strava.bulk_import_utils",
        "activity_media.service",
    ): "DEBT: Strava export sidecar photos are attached by calling the media service directly.",
    (
        "modules.users.users_profile.*",
        "activity_file_storage.service",
    ): "DEBT: profile export/import bundles retained source files without a published surface for them.",
    (
        "modules.users.users_profile.*",
        "activity_media.signing",
    ): "DEBT: profile export/import resolves media storage keys without a published surface for them.",
    (
        "*.models",
        "*.models",
    ): "SQLAlchemy relationships share one registry, so cross-module foreign keys must name each other.",
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
            # ``from modules.activities.activity import contracts`` names a
            # submodule; ``from ...activity.contracts import X`` names a symbol.
            if node.module.count(".") == 2:
                found.update(f"{node.module}.{alias.name}" for alias in node.names)
            else:
                found.add(node.module)
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
                    if imported_stem in _PUBLIC_WITHIN_MODULE:
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


class TestModuleSurface:
    """Other modules consume a module only through its published surface."""

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
                    if "." not in imported:
                        continue
                    if imported.rsplit(".", 1)[1] in _PUBLIC_ACROSS_MODULES:
                        continue
                    if _matches((importer, imported), _INBOUND_EXCEPTIONS):
                        continue
                    offenders.append(f"{importer} -> {module_name}.{imported}")
        assert not offenders, (
            "Reach past a module's published surface. Either add the operation "
            "to the module's integration_service, or record the exception in "
            "_INBOUND_EXCEPTIONS:\n  " + "\n  ".join(sorted(offenders))
        )
