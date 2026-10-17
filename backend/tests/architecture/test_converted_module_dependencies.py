"""What a converted module may take from ``core``, and which modules a hand-listed contract covers.

Two rules from ``docs/developer-guide/module-structure.md`` that import-linter
states badly:

* ``core.*`` is "always allowed", which makes it the largest hidden coupling
  between a module and this application. The allowlist below names every
  ``core`` module a converted module reaches today and why, so a new reach into
  application-wide state is a reviewed diff instead of an unnoticed import.
* ``auth-boundary`` names its source modules by hand, so a module is
  unconstrained until someone remembers to add it. The test fails on the
  difference.
"""

import ast
import configparser
import pathlib

from tests._helpers.module_roles import CONVERTED_MODULES, UNCONVERTED_MODULES

_MODULES_ROOT = pathlib.Path("app/modules")

_IMPORTLINTER = pathlib.Path(".importlinter")

#: ``core`` modules a converted module may import, as ``{core module: reason}``.
#: Generic primitives sit first; the entries below the divider read
#: application-wide state or wiring and are the ones to shrink, or to move into
#: ``jasil`` when they are generic enough to be shared by other products.
_ALLOWED_CORE: dict[str, str] = {
    "core.calendar": "Period boundaries for activity summaries.",
    "core.etag": "Conditional-response helpers for activity routes.",
    "core.event_metadata": "Event envelope metadata shared by every publisher.",
    "core.exceptions": "The domain error vocabulary raised by crud and service.",
    "core.file_uploads": "The only path an ``UploadFile`` may take.",
    "core.hashing": "Content digests for upload and media deduplication.",
    "core.logger": "Structured logging.",
    "core.pagination": "Page and cursor primitives.",
    "core.sanitization": "Cleaning user-supplied text before storage.",
    "core.signing": "The token-signing primitive behind thumbnail URLs.",
    "core.timezone": "Timezone resolution and conversion.",
    # Application-wide state or wiring: a declared dependency, not a free one.
    "core.config": "Environment-backed settings read directly rather than passed in.",
    "core.database": "Session dependency and declarative ``Base``; the metadata is still shared.",
    "core.dependencies": "``get_storage`` and id/type validators, resolved at the router edge.",
    "core.rate_limit": "Route-level rate limiting declared by routers.",
    "core.route_map": "Route-map render request used by thumbnail rendering.",
    "core.scheduler": "``ScheduledJob`` value type published by ``scheduled_jobs``.",
}


def _converted_files() -> list[pathlib.Path]:
    """Return every non-test source file of a converted module."""
    return sorted(
        path
        for module in CONVERTED_MODULES
        for path in (_MODULES_ROOT / module).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _core_imports(path: pathlib.Path) -> set[str]:
    """
    Return the ``core.<module>`` names a file imports.

    Args:
        path: The Python file to inspect.

    Returns:
        Two-segment names such as ``core.logger``; deeper paths collapse to
        their top-level ``core`` module.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [f"{node.module}.{alias.name}" if node.module == "core" else node.module for alias in node.names]
        else:
            continue
        for name in names:
            parts = name.split(".")
            if parts[0] == "core" and len(parts) > 1:
                found.add(".".join(parts[:2]))
    return found


class TestCoreAllowlist:
    """A converted module reaches only the ``core`` modules it has declared."""

    def test_converted_modules_import_only_allowlisted_core_modules(self):
        offenders = {
            f"{path.relative_to(_MODULES_ROOT)} -> {name}"
            for path in _converted_files()
            for name in _core_imports(path)
            if name not in _ALLOWED_CORE
        }
        assert not offenders, (
            "Converted modules import core modules that are not declared in _ALLOWED_CORE; add the entry with its "
            f"reason, or move the dependency behind a parameter: {sorted(offenders)}"
        )

    def test_allowlist_has_no_unused_entries(self):
        used = {name for path in _converted_files() for name in _core_imports(path)}
        stale = sorted(set(_ALLOWED_CORE) - used)
        assert not stale, f"Remove allowlist entries that no converted module imports any more: {stale}"


class TestAuthBoundaryCoverage:
    """The hand-listed ``auth-boundary`` sources cover every top-level module."""

    def test_auth_boundary_lists_every_module(self):
        parser = configparser.ConfigParser(allow_no_value=True, delimiters=("=",))
        parser.read(_IMPORTLINTER, encoding="utf-8")
        sources = {
            line.strip()
            for line in parser["importlinter:contract:auth-boundary"]["source_modules"].splitlines()
            if line.strip()
        }
        expected = {f"modules.{name}" for name in (*CONVERTED_MODULES, *UNCONVERTED_MODULES) if name != "auth"}
        expected.add("core")
        assert sources == expected, (
            "auth-boundary source_modules must list core and every top-level module except auth; "
            f"missing={sorted(expected - sources)} unexpected={sorted(sources - expected)}"
        )
