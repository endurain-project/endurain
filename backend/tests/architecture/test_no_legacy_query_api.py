"""The legacy ``Session.query(...)`` API is gone, and this test keeps it out.

Application code and tests use the SQLAlchemy 2 ``select()`` / ``update()`` / ``delete()`` statements with
``Session.execute``, ``Session.scalars``, ``Session.scalar`` and ``Session.get``. A ``.query(`` call on a session is
the 1.x API, so any ``<name>.query(...)`` call in ``app/`` or ``tests/`` fails, except on the distributed test
cluster, whose ``query`` method runs raw SQL.
"""

import ast
import pathlib

_ROOTS = (pathlib.Path("app"), pathlib.Path("tests"))

#: Receivers whose ``query`` method is not the ORM API.
_ALLOWED_RECEIVERS = frozenset({"cluster", "self"})


def _legacy_query_calls(path: pathlib.Path) -> list[int]:
    """Return the line numbers of ``<receiver>.query(...)`` calls on anything but an allowed receiver."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "query"
        and not (isinstance(node.func.value, ast.Name) and node.func.value.id in _ALLOWED_RECEIVERS)
    ]


def test_no_legacy_session_query_api() -> None:
    """No file under ``app/`` or ``tests/`` calls ``.query(...)`` on a session."""
    offenders = [
        f"{path}:{line}"
        for root in _ROOTS
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
        for line in _legacy_query_calls(path)
    ]
    assert not offenders, "use select()/update()/delete() instead of Session.query(): " + ", ".join(offenders)
