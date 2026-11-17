"""Tests for the settings sources the substrate reloads its providers from."""

from unittest.mock import MagicMock, patch

import jasil.settings as jasil_settings

import core.geocoding as core_geocoding
import core.mail as core_mail
import module_registry


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
