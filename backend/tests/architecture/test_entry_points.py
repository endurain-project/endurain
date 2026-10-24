"""Every process that serves requests or runs jobs installs the same contributor readers."""

import ast
import pathlib

import pytest

_APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"
_ENTRY_POINTS = ("main.py", "worker.py")
_REQUIRED_CALLS = ("configure_activity_contributors", "configure_gear_contributors")


def _called_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_entry_point_installs_every_contributor_registry(entry_point):
    missing = set(_REQUIRED_CALLS) - _called_names(_APP_ROOT / entry_point)

    assert not missing, f"{entry_point} does not call {sorted(missing)}; its requests or jobs would fail at runtime"
