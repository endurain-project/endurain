"""Structural invariants of the module template.

The activities and followers modules are the pattern the remaining modules are
being refactored towards, so the rules they establish are asserted here rather
than left to review. Each is something that has already gone wrong once.
"""

import ast
from pathlib import Path

import pytest

_MODULES_DIR = Path(__file__).resolve().parents[2] / "app" / "modules"
_TEMPLATE_PACKAGES = sorted(
    [*(_MODULES_DIR / "activities").glob("activity*"), _MODULES_DIR / "followers"],
)


def _init_files() -> list[Path]:
    return [pkg / "__init__.py" for pkg in _TEMPLATE_PACKAGES if (pkg / "__init__.py").is_file()]


@pytest.mark.parametrize("init_file", _init_files(), ids=lambda p: p.parent.name)
def test_package_init_is_a_docstring_only(init_file: Path) -> None:
    """A package facade must not re-export its ORM, CRUD or services.

    ``from modules.activities.activity_streams import ActivityStreamsModel`` was a
    legal way to obtain the ORM model, because import-linter matches
    ``modules.activities.activity_streams.models`` and a re-export hides that
    path. Every boundary contract written against ``*.models`` / ``*.crud`` had a
    hole next to it.
    """
    tree = ast.parse(init_file.read_text())
    offenders = [
        node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom | ast.Assign | ast.AnnAssign)
    ]
    assert not offenders, (
        f"{init_file.relative_to(_MODULES_DIR.parent)} should contain only a docstring. "
        "Re-exporting from a package facade bypasses the import-linter contracts that "
        "guard *.models and *.crud — import the submodule instead."
    )


def test_every_module_exposes_one_cross_module_surface_name() -> None:
    """The surface other modules may consume is always ``integration_service``.

    Followers used to expose it as ``service``, which also held its own
    privacy-checked application logic, so "what may I depend on?" had a different
    answer per module and consumers got the internals in scope too.
    """
    followers = _MODULES_DIR / "followers"
    assert (followers / "integration_service.py").is_file()
    assert (followers / "service.py").is_file()

    activity = _MODULES_DIR / "activities" / "activity"
    assert (activity / "integration_service.py").is_file()
    assert (activity / "service.py").is_file()
