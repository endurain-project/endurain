"""Structural invariants of the Alembic revision graph.

A branched graph is only discovered when a container boots and
``command.upgrade(cfg, "head")`` raises ``Multiple head revisions are present``,
which fails startup rather than CI. That happens whenever a new revision is
chained onto a stale head — most easily by adding it to a closed release
directory instead of the active one. These assertions move that failure to the
test run.
"""

from pathlib import Path

import pytest
from alembic.script import ScriptDirectory

from tests._helpers import alembic_chain

_APP_DIR = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture(scope="module")
def script_directory() -> ScriptDirectory:
    """Load the Alembic revision graph from the app's alembic.ini."""
    return alembic_chain.script_directory()


def test_revision_graph_has_exactly_one_head(script_directory: ScriptDirectory) -> None:
    heads = script_directory.get_heads()
    assert len(heads) == 1, (
        f"Alembic has {len(heads)} heads ({', '.join(sorted(heads))}). "
        "A new revision must chain onto the current head — check that its "
        "down_revision is the head of the ACTIVE release directory, not a closed one."
    )


def test_the_head_is_the_v0_22_speed_column_comments_revision() -> None:
    assert alembic_chain.script_directory().get_heads() == ["86ddd2645a0c"]


def test_the_history_is_the_baseline_and_the_five_v0_22_revisions() -> None:
    script = alembic_chain.script_directory()
    assert [revision.revision for revision in script.walk_revisions()] == [
        "86ddd2645a0c",
        "3c9e5a7d1f20",
        "8d2f61b0c7a4",
        "50ac9225ce4f",
        "b6cf67a93d94",
        alembic_chain.V0_21_HEAD,
    ]


def test_the_v0_22_chain_starts_from_the_v0_21_head() -> None:
    script = alembic_chain.script_directory()
    assert script.get_revision("b6cf67a93d94").down_revision == alembic_chain.V0_21_HEAD
    assert script.get_revision("50ac9225ce4f").down_revision == "b6cf67a93d94"
    assert script.get_revision("8d2f61b0c7a4").down_revision == "50ac9225ce4f"
    assert script.get_revision("3c9e5a7d1f20").down_revision == "8d2f61b0c7a4"
    assert script.get_revision("86ddd2645a0c").down_revision == "3c9e5a7d1f20"


def test_the_baseline_is_the_only_revision_without_a_parent() -> None:
    script = alembic_chain.script_directory()
    roots = [revision.revision for revision in script.walk_revisions() if revision.down_revision is None]
    assert roots == [alembic_chain.V0_21_HEAD]


def test_every_down_revision_resolves(script_directory: ScriptDirectory) -> None:
    revisions = {revision.revision for revision in script_directory.walk_revisions()}
    for revision in script_directory.walk_revisions():
        if revision.down_revision is None:
            continue
        parents = revision.down_revision if isinstance(revision.down_revision, tuple) else (revision.down_revision,)
        for parent in parents:
            assert parent in revisions, f"Revision {revision.revision} points at unknown down_revision {parent}"


def test_registered_data_migration_ids_are_unique() -> None:
    """Each ``INSERT INTO migrations`` must claim an unused id.

    The id is the primary key the data-migration runner keys off, so a duplicate
    fails the Alembic upgrade with an integrity error at startup. The baseline
    inserts its rows from a SQL script beside the revision, so both are read.
    """
    import re

    pattern = re.compile(r"INSERT INTO (?:public\.)?migrations[^;]*?VALUES\s*\((\d+),", re.IGNORECASE | re.DOTALL)
    seen: dict[str, Path] = {}
    versions = _APP_DIR / "alembic" / "versions"
    for path in [*versions.rglob("*.py"), *versions.rglob("*.sql")]:
        for migration_id in pattern.findall(path.read_text()):
            assert migration_id not in seen, (
                f"Data migration id {migration_id} is registered twice: {seen[migration_id].name} and {path.name}"
            )
            seen[migration_id] = path
    assert "7" in seen, "The baseline must register the v0.19.0 data migration"
