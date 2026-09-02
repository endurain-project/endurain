"""Tests for adopting the substrate's tables into its own migration history."""

from unittest.mock import MagicMock, patch

import jasil.orm as jasil_orm

import core.migrations as core_migrations


class TestBootstrapSubstrateSchema:
    def test_stamps_the_baseline_then_upgrades_when_tables_are_unversioned(self):
        # Both a fresh install and an existing one reach first boot the same way:
        # this application's Alembic history created the tables, and the
        # substrate's version table does not exist yet.
        with (
            patch("core.migrations.jasil_migrations") as migrations,
            patch("core.migrations.substrate_tables_exist", return_value=True),
        ):
            migrations.db_revision.return_value = None
            core_migrations.bootstrap_substrate_schema()

        migrations.stamp.assert_called_once_with(core_migrations.engine, "rev0001")
        migrations.upgrade.assert_called_once_with(core_migrations.engine)

    def test_stamps_the_baseline_not_head(self):
        # Stamping head would record revisions that never ran, so a later JASIL
        # release's migrations would be skipped instead of applied.
        with (
            patch("core.migrations.jasil_migrations") as migrations,
            patch("core.migrations.substrate_tables_exist", return_value=True),
        ):
            migrations.db_revision.return_value = None
            migrations.head_revision.return_value = "rev0009"
            core_migrations.bootstrap_substrate_schema()

        assert migrations.stamp.call_args.args[1] == "rev0001"

    def test_does_not_stamp_an_already_adopted_database(self):
        with (
            patch("core.migrations.jasil_migrations") as migrations,
            patch("core.migrations.substrate_tables_exist", return_value=True),
        ):
            migrations.db_revision.return_value = "rev0001"
            core_migrations.bootstrap_substrate_schema()

        migrations.stamp.assert_not_called()
        migrations.upgrade.assert_called_once_with(core_migrations.engine)

    def test_does_not_stamp_a_database_without_the_tables(self):
        # Nothing to adopt, so the substrate creates them from its own base.
        with (
            patch("core.migrations.jasil_migrations") as migrations,
            patch("core.migrations.substrate_tables_exist", return_value=False),
        ):
            migrations.db_revision.return_value = None
            core_migrations.bootstrap_substrate_schema()

        migrations.stamp.assert_not_called()
        migrations.upgrade.assert_called_once_with(core_migrations.engine)

    def test_baseline_is_the_substrates_base_revision(self):
        # The tables this application's history creates are the substrate's
        # *base* shape. If JASIL ever re-bases its history, stamping the old id
        # would silently record a revision that no longer exists, so the
        # assumption is checked against the installed release rather than held.
        import pathlib

        import jasil.migrations as jasil_migrations
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config()
        config.set_main_option("script_location", str(pathlib.Path(jasil_migrations.__file__).parent))

        assert ScriptDirectory.from_config(config).get_base() == core_migrations.SUBSTRATE_BASELINE_REVISION


class TestSubstrateTablesExist:
    def test_checks_every_table_the_substrate_owns(self):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        with patch("core.migrations.sa.inspect", return_value=inspector):
            assert core_migrations.substrate_tables_exist() is True

        checked = {call.args[0] for call in inspector.has_table.call_args_list}
        assert checked == set(jasil_orm.jasil_table_names())

    def test_false_when_any_table_is_missing(self):
        inspector = MagicMock()
        inspector.has_table.side_effect = [True, False, True]
        with patch("core.migrations.sa.inspect", return_value=inspector):
            assert core_migrations.substrate_tables_exist() is False
