"""Structural invariants of the Alembic revision graph.

A branched graph is only discovered when a container boots and
``command.upgrade(cfg, "head")`` raises ``Multiple head revisions are present``,
which fails startup rather than CI. That happens whenever a new revision is
chained onto a stale head — most easily by adding it to a closed release
directory instead of the active one. These assertions move that failure to the
test run.
"""

import pytest
from alembic.script import ScriptDirectory
from tests._helpers import alembic_chain


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


def test_the_head_is_the_v0_22_retirement_revision() -> None:
    assert alembic_chain.script_directory().get_heads() == ["50ac9225ce4f"]


def test_the_history_is_the_baseline_and_the_two_v0_22_revisions() -> None:
    script = alembic_chain.script_directory()
    assert [revision.revision for revision in script.walk_revisions()] == [
        "50ac9225ce4f",
        "b6cf67a93d94",
        alembic_chain.V0_21_HEAD,
    ]


def test_the_v0_22_chain_starts_from_the_v0_21_head() -> None:
    script = alembic_chain.script_directory()
    assert script.get_revision("b6cf67a93d94").down_revision == alembic_chain.V0_21_HEAD
    assert script.get_revision("50ac9225ce4f").down_revision == "b6cf67a93d94"


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
