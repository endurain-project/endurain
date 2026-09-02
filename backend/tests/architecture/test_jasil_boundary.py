"""The application consumes JASIL's public surface, never its internals.

``.importlinter`` cannot express this rule: JASIL is an external package, and
import-linter rejects a *subpackage* of an external package as a forbidden
module. So it is checked here instead, the same way the sub-package privacy
rules are — walk the AST of every application file and compare each import
against the private surface.

What is private, and why:

``jasil._core``
    Documented as internal; it carries no API-stability promise across the
    pre-1.0 minor releases this project pins against.
``jasil.backends``
    The concrete adapters. Importing one re-couples the domain to Redis, S3 or
    the local filesystem, which is precisely what depending on the capability
    providers exists to avoid.
``jasil.jobs.crud`` / ``jasil.event_log.crud``
    Both reach a model at import time (so importing one before
    ``jasil.orm.map_models`` has run raises) and both commit whatever session
    they are handed — including an admin request's own uncommitted work.
    ``jasil.admin`` is the seam that opens a short-lived session of its own.
"""

import ast
import pathlib

import pytest

_APP_ROOT = pathlib.Path("app")

_PRIVATE_SURFACE = (
    "jasil._core",
    "jasil.backends",
    "jasil.jobs.crud",
    "jasil.event_log.crud",
)


def _python_files(root: pathlib.Path) -> list[pathlib.Path]:
    """
    Return the Python files under a directory.

    Args:
        root: The directory to walk.

    Returns:
        The sorted list of ``.py`` files, excluding caches.
    """
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_modules(path: pathlib.Path) -> set[str]:
    """
    Return every dotted module path this file imports.

    Args:
        path: The Python file to parse.

    Returns:
        The imported dotted module paths, including ``TYPE_CHECKING`` imports.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _violations() -> list[str]:
    """Return every application import that reaches JASIL's private surface."""
    offences: list[str] = []
    for path in _python_files(_APP_ROOT):
        for imported in sorted(_imported_modules(path)):
            if any(imported == private or imported.startswith(f"{private}.") for private in _PRIVATE_SURFACE):
                offences.append(f"{path} -> {imported}")
    return offences


class TestJasilBoundary:
    def test_application_does_not_import_jasil_internals(self):
        offences = _violations()
        assert not offences, "Application code must use JASIL's public surface:\n" + "\n".join(offences)

    @pytest.mark.parametrize("private", _PRIVATE_SURFACE)
    def test_the_private_surface_still_exists(self, private):
        # A rule that names a module JASIL has since moved or renamed silently
        # stops protecting anything, so the names are pinned to the installed
        # release rather than assumed.
        __import__(private)
