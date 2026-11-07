"""The platform layer sits below the application: ``core`` never reaches up into it."""

import ast
import pathlib

_CORE = pathlib.Path("app/core")

#: Top-level packages and modules of the application layer, which ``core`` must not import.
_APPLICATION = {"api", "main", "migrations", "model_registry", "module_registry", "modules", "worker"}


def test_core_imports_nothing_from_the_application_layer():
    """Import-linter only sees ``core`` and ``modules``, so the other application packages are checked here."""
    offenders: list[str] = []
    for path in sorted(_CORE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else []
            )
            offenders.extend(
                f"{path}:{node.lineno} imports {name}" for name in names if name.split(".")[0] in _APPLICATION
            )

    assert offenders == [], "\n".join(offenders)
