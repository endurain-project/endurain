"""Tests for the follower blocks and declines migration (revision 53)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/53_follower_blocks_and_declines.py"
)


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("follower_blocks_and_declines", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "c3d9a5e1f478"


def test_upgrade_creates_both_tables_with_their_unique_pairs() -> None:
    migration = _migration_module()

    with patch.object(migration.op, "create_table") as create_table, patch.object(migration.op, "create_index"):
        migration.upgrade()

    created = {call.args[0]: call.args[1:] for call in create_table.call_args_list}
    assert set(created) == {"follower_blocks", "follow_request_declines"}
    unique_names = {
        table: {item.name for item in items if type(item).__name__ == "UniqueConstraint"}
        for table, items in created.items()
    }
    assert unique_names == {
        "follower_blocks": {"uq_follower_blocks_blocker_blocked"},
        "follow_request_declines": {"uq_follow_request_declines_follower_followee"},
    }


def test_downgrade_drops_both_tables() -> None:
    migration = _migration_module()

    with patch.object(migration.op, "drop_index"), patch.object(migration.op, "drop_table") as drop_table:
        migration.downgrade()

    assert {call.args[0] for call in drop_table.call_args_list} == {"follower_blocks", "follow_request_declines"}
