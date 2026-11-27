"""The application's Alembic history keeps off the tables the substrate owns.

``jasil.orm.map_models`` maps ``event_log``, ``event_outbox`` and
``processing_jobs`` into the same declarative registry as this application's own
models, which is what lets one metadata object and one connection cover the
whole schema. The cost is that autogenerate here sees them too, and would
propose managing -- eventually dropping -- tables it does not own.

``env.py`` filters them out through ``migrations.schema_scope.include_object``.
Without a test, that filter failing is invisible until an autogenerate run
produces a destructive revision.
"""

import pathlib

import jasil.orm as jasil_orm
import pytest

from migrations.schema_scope import include_object

_ENV_PATH = pathlib.Path("app/alembic/env.py")


class TestIncludeObject:
    @pytest.mark.parametrize("table", sorted(jasil_orm.jasil_table_names()))
    def test_excludes_every_substrate_table(self, table):
        assert include_object(None, table, "table", True, None) is False

    @pytest.mark.parametrize("table", sorted(jasil_orm.legacy_table_names()))
    def test_excludes_every_unprefixed_legacy_substrate_table(self, table):
        assert include_object(None, table, "table", True, None) is False

    def test_excludes_the_substrate_version_table(self):
        assert include_object(None, "jasil_alembic_version", "table", True, None) is False

    def test_excludes_an_audit_log_partition(self):
        assert include_object(None, "jasil_audit_log_p20261112", "table", True, None) is False

    def test_excludes_the_upgrade_scratch_table_of_the_uuid_conversion(self):
        assert include_object(None, "uuid_migration_ids", "table", True, None) is False

    @pytest.mark.parametrize("table", ["users", "migrations"])
    def test_keeps_application_tables(self, table):
        assert include_object(None, table, "table", True, None) is True

    def test_keeps_non_table_objects(self):
        # Columns and indexes are reached through their table, which is already
        # excluded; filtering them by name here would drop host objects that
        # happen to share a name.
        assert include_object(None, "ix_users_id", "index", True, None) is True
        assert include_object(None, "created_at", "column", True, None) is True
        assert include_object(None, "jasil_event_log", "index", True, None) is True


class TestConfiguredOnBothPaths:
    @pytest.mark.parametrize("path", ["offline", "online"])
    def test_context_configure_passes_include_object(self, path):
        # Autogenerate runs online, but a filter wired into only one path is a
        # trap for whoever next runs offline.
        source = _ENV_PATH.read_text()
        body = source.split(f"def run_migrations_{path}")[1].split("\ndef ")[0]
        assert "include_object=include_object" in body
