"""Nothing reads ``activities.dedup_key`` or the two legacy provider id columns; the release that drops them is clean.

An activity is identified by its ``activity_sources`` and reads its Strava and Garmin Connect ids from them. The
columns stay, nullable, so dropping them is plain DDL: ``dedup_key`` is neither written nor read, and the provider id
columns are written by ``to_orm`` alone, as ``legacy_*`` attributes, and read by no code.
"""

import ast
import pathlib

import pytest

_APP = pathlib.Path("app")

#: Where each legacy name may appear: its mapped attribute in the model, and for the provider id columns the one
#: serializer that writes them. The schema revisions are history and out of scope.
_ALLOWED: dict[str, frozenset[str]] = {
    "dedup_key": frozenset({"modules/activities/activity/models.py"}),
    "legacy_strava_activity_id": frozenset(
        {"modules/activities/activity/models.py", "modules/activities/activity/serializers.py"}
    ),
    "legacy_garminconnect_activity_id": frozenset(
        {"modules/activities/activity/models.py", "modules/activities/activity/serializers.py"}
    ),
}


def _uses(path: pathlib.Path, name: str) -> list[int]:
    """Return the lines where a file uses a name as an attribute, a keyword argument or a bare name."""
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (
            (isinstance(node, ast.Attribute) and node.attr == name)
            or (isinstance(node, ast.keyword) and node.arg == name)
            or (isinstance(node, ast.Name) and node.id == name)
        ):
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("name", sorted(_ALLOWED))
def test_the_legacy_column_is_used_nowhere_but_where_it_is_declared_or_written(name):
    offenders = []
    for path in sorted(_APP.rglob("*.py")):
        relative = path.relative_to(_APP).as_posix()
        if relative.startswith("alembic/") or relative in _ALLOWED[name]:
            continue
        offenders += [f"{relative}:{line}" for line in _uses(path, name)]

    assert offenders == [], f"{name} is a legacy column that nothing may read or write: {offenders}"


def test_the_serializer_writes_the_provider_id_columns_and_reads_none():
    path = _APP / "modules/activities/activity/serializers.py"

    for name in ("legacy_strava_activity_id", "legacy_garminconnect_activity_id"):
        used = [node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if _is_write(node, name)]
        reads = [
            node
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Attribute) and node.attr == name
        ]
        assert len(used) == 1
        assert reads == []


def _is_write(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.keyword) and node.arg == name
