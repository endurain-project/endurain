"""The settings sources the substrate reloads its providers from, read from the stored operator settings."""

import jasil.settings as jasil_settings
import pytest
from sqlalchemy import text

import core.exceptions as core_exceptions
import module_registry
from tests._factories.server_settings import edit_mail_settings, edit_server_settings


def _store_mail(committed_sessions, **fields) -> None:
    with committed_sessions() as db:
        edit_mail_settings(db, **fields)
        db.commit()


class TestMailSource:
    def test_the_stored_config_is_mapped(self, committed_sessions):
        _store_mail(
            committed_sessions, host="mail.example.com", port=465, security="ssl", from_address="me@example.com"
        )

        result = module_registry.runtime_sources().mail()

        assert result.uri == "smtps://mail.example.com:465"

    def test_mail_is_unset_while_it_is_disabled(self, committed_sessions):
        assert module_registry.runtime_sources().mail() == jasil_settings.MailSettings()

    def test_a_change_is_seen_after_the_cache_window_not_before(self, committed_sessions, monkeypatch):
        source = module_registry.runtime_sources().mail
        assert source() == jasil_settings.MailSettings()
        _store_mail(committed_sessions, host="mail.example.com", port=465, security="ssl", from_address="me@x.com")

        assert source() == jasil_settings.MailSettings()
        monkeypatch.setattr(module_registry, "_SETTINGS_CACHE_SECONDS", 0)
        assert source().uri == "smtps://mail.example.com:465"

    def test_a_failed_read_is_not_swallowed_nor_cached(self, committed_sessions):
        """The substrate decides what a failing source means; the host must let it see the error."""
        _store_mail(committed_sessions, host="mail.example.com", port=465, security="ssl", from_address="me@x.com")
        with committed_sessions() as db:
            db.execute(text("UPDATE mail_settings SET password = 'not-a-fernet-token'"))
            db.commit()
        source = module_registry.runtime_sources().mail

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            source()

        with committed_sessions() as db:
            db.execute(text("UPDATE mail_settings SET password = NULL"))
            db.commit()
        assert source().uri == "smtps://mail.example.com:465"


class TestGeocodingSource:
    def test_the_stored_config_is_mapped(self, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(
                db,
                geocoding_service="photon",
                geocoding_host="photon.example.com",
                geocoding_use_https=True,
                geocoding_rate_limit=2.0,
            )
            db.commit()

        result = module_registry.runtime_sources().geocoding()

        assert result.uri == "photon://photon.example.com"

    def test_a_service_without_a_host_uses_its_public_instance(self, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, geocoding_service="photon", geocoding_host=None)
            db.commit()

        assert module_registry.runtime_sources().geocoding().uri == "photon://photon.komoot.io"

    def test_missing_settings_leave_geocoding_unset(self, committed_sessions):
        with committed_sessions() as db:
            db.execute(text("DELETE FROM server_settings"))
            db.commit()

        assert module_registry.runtime_sources().geocoding() == jasil_settings.GeocodingSettings()
