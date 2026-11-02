"""The route handlers of the converted modules, read from source.

Shared by the conformance tests that hold every route to a rule (``tests/architecture/test_route_conventions.py``,
``tests/architecture/test_audit_trail.py``), so they agree on what a route and a write route are.
"""

import ast
import pathlib

from tests._helpers.module_roles import CONVERTED_MODULES, files_with_role

MODULES_ROOT = pathlib.Path("app/modules")

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
WRITE_METHODS = frozenset({"post", "put", "patch", "delete"})


def route_decorators(function: ast.AST):
    """Yield ``(method, call)`` for each HTTP route decorator on a function."""
    for decorator in getattr(function, "decorator_list", []):
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in HTTP_METHODS
        ):
            yield decorator.func.attr, decorator


def router_functions() -> list[tuple[pathlib.Path, ast.FunctionDef]]:
    """Return every route handler of every converted module."""
    roots = tuple(MODULES_ROOT / name for name in CONVERTED_MODULES)
    found: list[tuple[pathlib.Path, ast.FunctionDef]] = []
    for role in ("router", "public_router"):
        for path in files_with_role(roots, role):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.FunctionDef) and any(True for _ in route_decorators(node)):
                    found.append((path, node))
    return found
