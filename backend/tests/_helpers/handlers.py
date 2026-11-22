"""Helpers for the architecture tests that walk ``except`` handlers."""

import ast
from collections.abc import Iterator


def own_nodes(handler: ast.ExceptHandler) -> Iterator[ast.AST]:
    """Yield the nodes of an ``except`` body, leaving nested handlers to be judged on their own."""
    stack = list(handler.body)
    while stack:
        node = stack.pop()
        yield node
        stack.extend(child for child in ast.iter_child_nodes(node) if not isinstance(child, ast.ExceptHandler))
