"""The application's Alembic history keeps off the tables the substrate owns.

``jasil.orm.map_models`` maps ``event_log``, ``event_outbox`` and
``processing_jobs`` into the same declarative registry as this application's own
models, which is what lets one metadata object and one connection cover the
whole schema. The cost is that autogenerate here sees them too, and would
propose managing -- eventually dropping -- tables it does not own.

``env.py`` filters them out through ``include_object``. Without a test, that
filter failing is invisible until an autogenerate run produces a destructive
revision.
"""

import ast
import pathlib

import jasil.orm as jasil_orm
import pytest

_ENV_PATH = pathlib.Path("app/alembic/env.py")


def _load_include_object():
    """Compile ``include_object`` out of env.py in isolation.

    env.py's module body reaches for a live Alembic migration context, so the
    function is lifted from the real source rather than the module imported.
    """
    tree = ast.parse(_ENV_PATH.read_text())
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "include_object")
    namespace: dict = {"jasil_orm": jasil_orm}
    # Compiling one function out of a file in this repository, so the test reads
    # the shipped hook rather than a copy that can drift from it.
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(_ENV_PATH), "exec"), namespace)  # noqa: S102
    return namespace["include_object"]


@pytest.fixture(scope="module")
def include_object():
    return _load_include_object()


class TestIncludeObject:
    @pytest.mark.parametrize("table", sorted(jasil_orm.jasil_table_names()))
    def test_excludes_every_substrate_table(self, include_object, table):
        assert include_object(None, table, "table", True, None) is False

    def test_keeps_application_tables(self, include_object):
        assert include_object(None, "users", "table", True, None) is True

    def test_keeps_non_table_objects(self, include_object):
        # Columns and indexes are reached through their table, which is already
        # excluded; filtering them by name here would drop host objects that
        # happen to share a name.
        assert include_object(None, "ix_users_id", "index", True, None) is True
        assert include_object(None, "created_at", "column", True, None) is True


class TestConfiguredOnBothPaths:
    @pytest.mark.parametrize("path", ["offline", "online"])
    def test_context_configure_passes_include_object(self, path):
        # Autogenerate runs online, but a filter wired into only one path is a
        # trap for whoever next runs offline.
        source = _ENV_PATH.read_text()
        body = source.split(f"def run_migrations_{path}")[1].split("\ndef ")[0]
        assert "include_object=include_object" in body
