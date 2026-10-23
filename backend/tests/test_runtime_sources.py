"""Tests for the settings sources the substrate reloads its providers from."""

from unittest.mock import MagicMock, patch

import jasil.settings as jasil_settings

import core.mail as core_mail
import module_registry


class TestRuntimeSources:
    def test_mail_is_runtime_configured(self):
        sources = module_registry.runtime_sources()

        assert sources.mail is not None
        assert sources.geocoding is None

    def test_the_mail_source_maps_the_stored_config(self):
        config = core_mail.MailConfig(
            host="mail.example.com",
            port=465,
            security=core_mail.MailSecurity.SSL,
            from_address="me@example.com",
        )
        with (
            patch.object(module_registry.core_database, "SessionLocal") as session_local,
            patch.object(module_registry.server_settings_integration, "get_mail_config", return_value=config) as read,
        ):
            result = module_registry.runtime_sources().mail()

        assert result.uri == "smtps://mail.example.com:465"
        read.assert_called_once_with(session_local.return_value.__enter__.return_value)

    def test_the_mail_source_is_unset_when_mail_is_disabled(self):
        with (
            patch.object(module_registry.core_database, "SessionLocal", return_value=MagicMock()),
            patch.object(module_registry.server_settings_integration, "get_mail_config", return_value=None),
        ):
            assert module_registry.runtime_sources().mail() == jasil_settings.MailSettings()

    def test_the_mail_source_does_not_swallow_a_failed_read(self):
        """The substrate decides what a failing source means; the host must let it see the error."""
        with (
            patch.object(module_registry.core_database, "SessionLocal", return_value=MagicMock()),
            patch.object(module_registry.server_settings_integration, "get_mail_config", side_effect=RuntimeError),
        ):
            try:
                module_registry.runtime_sources().mail()
            except RuntimeError:
                return
        raise AssertionError("the failure was swallowed")
