"""Tests for delegating substrate schema ownership to JASIL."""

from unittest.mock import call, patch

import core.migrations as core_migrations


class TestBootstrapSubstrateSchema:
    def test_adopts_then_upgrades_and_verifies(self):
        with patch("core.migrations.jasil_migrations") as migrations:
            core_migrations.bootstrap_substrate_schema()

        assert migrations.method_calls == [
            call.adopt_existing_schema(core_migrations.engine),
            call.upgrade(core_migrations.engine),
            call.verify_schema_current(core_migrations.engine),
        ]

    def test_logs_when_legacy_tables_are_adopted(self):
        with (
            patch("core.migrations.jasil_migrations") as migrations,
            patch("core.migrations.logger") as logger,
        ):
            migrations.adopt_existing_schema.return_value = True
            core_migrations.bootstrap_substrate_schema()

        logger.info.assert_called_once()

    def test_is_silent_when_no_adoption_occurs(self):
        with (
            patch("core.migrations.jasil_migrations") as migrations,
            patch("core.migrations.logger") as logger,
        ):
            migrations.adopt_existing_schema.return_value = False
            core_migrations.bootstrap_substrate_schema()

        logger.info.assert_not_called()
