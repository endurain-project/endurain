"""Tests for the settings sources the substrate reloads its providers from."""

from unittest.mock import MagicMock, patch

import jasil.audit as jasil_audit
import jasil.settings as jasil_settings
import pytest

import core.geocoding as core_geocoding
import core.mail as core_mail
import module_registry
import modules.server_settings.contracts as server_settings_contracts


class TestRuntimeSources:
    def test_mail_is_runtime_configured(self):
        sources = module_registry.runtime_sources()

        assert sources.mail is not None
        assert sources.geocoding is not None

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


class TestStoragePlainAreas:
    def test_every_area_is_plain_on_local_storage(self):
        assert module_registry.storage_plain_areas() == frozenset(
            {
                "activity_files",
                "activity_media",
                "activity_thumbnails",
                "bulk_import_errors",
                "profile_export_staging",
                "profile_import_staging",
                "server_images",
                "identity_provider_icons",
                "user_images",
            }
        )


class TestGeocodingSource:
    def test_the_geocoding_source_maps_the_stored_config(self):
        config = core_geocoding.GeocodingConfig(
            service=core_geocoding.GeocodingService.PHOTON, host="photon.example.com", use_https=True, rate_limit=2.0
        )
        with (
            patch.object(module_registry.core_database, "SessionLocal") as session_local,
            patch.object(
                module_registry.server_settings_integration, "get_geocoding_config", return_value=config
            ) as read,
        ):
            result = module_registry.runtime_sources().geocoding()

        assert result.uri == "photon://photon.example.com"
        read.assert_called_once_with(session_local.return_value.__enter__.return_value)

    def test_the_geocoding_source_is_unset_without_a_config(self):
        with (
            patch.object(module_registry.core_database, "SessionLocal", return_value=MagicMock()),
            patch.object(module_registry.server_settings_integration, "get_geocoding_config", return_value=None),
        ):
            assert module_registry.runtime_sources().geocoding() == jasil_settings.GeocodingSettings()


class TestAuditRetentionSource:
    @staticmethod
    def _installed_source():
        """Run ``configure_audit`` and return the retention source it installs."""
        with (
            patch.object(module_registry.jasil_audit, "get_catalog"),
            patch.object(module_registry.jasil_audit, "configure_provider"),
            patch.object(module_registry.jasil_audit, "configure_retention_source") as install,
        ):
            module_registry.configure_audit()
        install.assert_called_once()
        return install.call_args.args[0]

    def test_configure_audit_installs_the_stored_retention(self):
        stored = server_settings_contracts.AuditRetention(retention_days=365, legal_hold=True)
        source = self._installed_source()
        with (
            patch.object(module_registry.core_database, "SessionLocal") as session_local,
            patch.object(
                module_registry.server_settings_integration, "get_audit_retention", return_value=stored
            ) as read,
        ):
            result = source()

        assert result == jasil_audit.AuditRetention(retention_days=365, legal_hold=True)
        read.assert_called_once_with(session_local.return_value.__enter__.return_value)

    def test_the_source_is_cached_between_maintenance_runs(self):
        stored = server_settings_contracts.AuditRetention(retention_days=0, legal_hold=False)
        source = self._installed_source()
        with (
            patch.object(module_registry.core_database, "SessionLocal", return_value=MagicMock()),
            patch.object(
                module_registry.server_settings_integration, "get_audit_retention", return_value=stored
            ) as read,
        ):
            assert source() == source()

        read.assert_called_once()

    def test_the_source_does_not_swallow_a_failed_read(self):
        """Maintenance logs the failure and seals and prunes nothing, which it can only do if it sees the error."""
        source = self._installed_source()
        with (
            patch.object(module_registry.core_database, "SessionLocal", return_value=MagicMock()),
            patch.object(module_registry.server_settings_integration, "get_audit_retention", side_effect=RuntimeError),
            pytest.raises(RuntimeError),
        ):
            source()
