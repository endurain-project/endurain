"""Event payloads reach the outbox and the event bus through ``json.dumps``, so publishers dump in JSON mode.

A python-mode ``model_dump()`` keeps ``datetime`` values that ``json.dumps`` rejects (jasil turns a ``uuid.UUID`` into
its string itself). Dumping in JSON mode everywhere keeps one rule. Every ``.model_dump(...)`` call in a module that imports ``jasil.publisher`` must pass ``mode="json"``.
"""

import ast
import pathlib

import pytest

_APP_ROOT = pathlib.Path("app")


def _imports_publisher(tree: ast.AST) -> bool:
    """
    Return whether a module imports ``jasil.publisher``.

    Args:
        tree: The parsed module.

    Returns:
        True when the module imports ``jasil.publisher`` or something from it.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "jasil.publisher" for alias in node.names):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (
                node.module == "jasil.publisher"
                or (node.module == "jasil" and any(alias.name == "publisher" for alias in node.names))
            )
        ):
            return True
    return False


def _publisher_modules() -> list[pathlib.Path]:
    """
    Return the application files that import ``jasil.publisher``.

    Returns:
        The sorted paths of those files.
    """
    found = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        if _imports_publisher(ast.parse(path.read_text(encoding="utf-8"))):
            found.append(path)
    return found


def _is_json_mode(call: ast.Call) -> bool:
    """
    Return whether a call passes the keyword ``mode="json"`` as a constant.

    Args:
        call: The ``model_dump`` call.

    Returns:
        True when ``mode="json"`` is present.
    """
    return any(
        keyword.arg == "mode" and isinstance(keyword.value, ast.Constant) and keyword.value.value == "json"
        for keyword in call.keywords
    )


def test_publisher_modules_are_found() -> None:
    """The scan covers the publisher modules, so an empty result cannot pass silently."""
    assert _publisher_modules()


@pytest.mark.parametrize("path", _publisher_modules(), ids=str)
def test_model_dump_uses_json_mode(path: pathlib.Path) -> None:
    """Every ``.model_dump(...)`` call in a publishing module passes ``mode="json"``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        f"{path}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "model_dump"
        and not _is_json_mode(node)
    ]
    assert not offenders, f'model_dump() without mode="json": {", ".join(offenders)}'
