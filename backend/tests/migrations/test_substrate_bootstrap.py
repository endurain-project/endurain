"""Tests for delegating substrate schema ownership to JASIL."""

from unittest.mock import call, patch

import migrations.startup as migrations_startup

_ENGINE = object()


class TestBootstrapSubstrateSchema:
    def test_adopts_then_upgrades_and_verifies(self):
        with patch("migrations.startup.jasil_migrations") as migrations:
            migrations_startup.bootstrap_substrate_schema(_ENGINE)

        assert migrations.method_calls == [
            call.adopt_existing_schema(_ENGINE),
            call.upgrade(_ENGINE),
            call.verify_schema_current(_ENGINE),
        ]

    def test_logs_when_legacy_tables_are_adopted(self):
        with (
            patch("migrations.startup.jasil_migrations") as migrations,
            patch("migrations.startup.logger") as logger,
        ):
            migrations.adopt_existing_schema.return_value = True
            migrations_startup.bootstrap_substrate_schema(_ENGINE)

        logger.info.assert_called_once()

    def test_is_silent_when_no_adoption_occurs(self):
        with (
            patch("migrations.startup.jasil_migrations") as migrations,
            patch("migrations.startup.logger") as logger,
        ):
            migrations.adopt_existing_schema.return_value = False
            migrations_startup.bootstrap_substrate_schema(_ENGINE)

        logger.info.assert_not_called()
