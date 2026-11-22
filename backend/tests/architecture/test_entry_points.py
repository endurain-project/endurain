"""Every process that serves requests or runs jobs installs the same contributors and providers."""

import ast
import pathlib

import pytest

_APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"
_ENTRY_POINTS = ("main.py", "worker.py")
_SHARED_SETUP = "configure_application"
_REQUIRED_CALLS = (
    "configure_activity_contributors",
    "configure_gear_contributors",
    "configure_user_contributors",
    "register_activity_provider",
)


def _called_names(node: ast.AST) -> set[str]:
    return {
        child.func.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
    } | {child.func.id for child in ast.walk(node) if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)}


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_entry_point_runs_the_shared_setup(entry_point):
    called = _called_names(ast.parse((_APP_ROOT / entry_point).read_text()))

    assert _SHARED_SETUP in called, f"{entry_point} does not call {_SHARED_SETUP}(); its requests or jobs would fail"


def test_the_shared_setup_installs_every_contributor_and_provider():
    tree = ast.parse((_APP_ROOT / "module_registry.py").read_text())
    setup = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == _SHARED_SETUP)

    missing = set(_REQUIRED_CALLS) - _called_names(setup)

    assert not missing, f"{_SHARED_SETUP} does not call {sorted(missing)}"


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_entry_point_does_not_install_pieces_of_the_setup_itself(entry_point):
    """A piece installed by hand in one entry point is how the two drift apart again."""
    called = _called_names(ast.parse((_APP_ROOT / entry_point).read_text()))

    assert not set(_REQUIRED_CALLS) & called


#: Module pools an entry point once stopped by hand; each now comes from its module's ``shutdown`` hook.
_POOL_SHUTDOWNS = (
    "shutdown_background_ingestion",
    "shutdown_pools",
    "shutdown_transfer_pool",
    "shutdown_deletion_pool",
    "shutdown_bulk_edit_pool",
)


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_entry_point_releases_every_module_pool_through_the_registry(entry_point):
    """One list of what each module must release, so a pool added to a module is never left running."""
    called = _called_names(ast.parse((_APP_ROOT / entry_point).read_text()))

    assert "shutdown_module_pools" in called
    assert not set(_POOL_SHUTDOWNS) & called
