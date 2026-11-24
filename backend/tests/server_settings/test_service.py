"""What the rest of the application reads from the settings rows, against the migrated schema."""

from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, update

import core.config as core_config
import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.geocoding as core_geocoding
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.models as server_settings_models
import modules.server_settings.scheduled_jobs as server_settings_scheduled_jobs
import modules.server_settings.service as server_settings_service
from tests._factories.server_settings import edit_mail_settings, edit_server_settings

_NEW_KEY = Fernet.generate_key().decode()
_OLD_KEY = Fernet.generate_key().decode()


def _without_settings_row(db) -> None:
    db.execute(delete(server_settings_models.ServerSettings))


class TestSessionPolicy:
    def test_the_enforced_timeouts_and_the_lifetimes_come_from_the_stored_settings(self, db):
        edit_server_settings(
            db,
            session_idle_timeout_enabled=True,
            session_idle_timeout_hours=2,
            session_absolute_timeout_hours=24,
            access_token_expire_minutes=30,
            refresh_token_expire_days=14,
            api_key_max_lifetime_days=60,
        )

        policy = server_settings_integration.get_session_policy(db)

        assert policy.access_token_ttl == timedelta(minutes=30)
        assert policy.refresh_token_ttl == timedelta(days=14)
        assert policy.idle_timeout == timedelta(hours=2)
        assert policy.absolute_timeout == timedelta(hours=24)
        assert policy.api_key_max_lifetime == timedelta(days=60)

    def test_a_disabled_idle_timeout_is_none_while_the_absolute_timeout_still_applies(self, db):
        edit_server_settings(db, session_idle_timeout_enabled=False, session_absolute_timeout_hours=100)

        policy = server_settings_integration.get_session_policy(db)

        assert policy.idle_timeout is None
        assert policy.absolute_timeout == timedelta(hours=100)

    def test_a_missing_settings_row_is_a_service_error(self, db):
        _without_settings_row(db)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_integration.get_session_policy(db)


class TestAccessPolicy:
    @pytest.mark.parametrize("value", ["off", "administrators", "everyone"])
    def test_it_carries_the_session_policy_and_the_mfa_requirement_from_one_read(self, db, value):
        edit_server_settings(db, require_mfa=value)

        policy = server_settings_integration.get_access_policy(db)

        assert policy.require_mfa == server_settings_contracts.RequireMfa(value)
        assert policy.session.access_token_ttl == timedelta(minutes=15)

    def test_a_missing_settings_row_is_a_service_error(self, db):
        _without_settings_row(db)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_integration.get_access_policy(db)

    @pytest.mark.parametrize(
        ("value", "admin", "regular"),
        [("off", False, False), ("administrators", True, False), ("everyone", True, True)],
    )
    def test_each_requirement_covers_its_accounts(self, value, admin, regular):
        requirement = server_settings_contracts.RequireMfa(value)

        assert requirement.covers(is_admin=True) is admin
        assert requirement.covers(is_admin=False) is regular


class TestIntegrationReads:
    def test_the_settings_other_modules_read_never_carry_the_api_keys(self, db):
        edit_server_settings(db, tileserver_api_key="tile-key", geocoding_api_key="geo-key", signup_enabled=True)

        settings = server_settings_integration.get_server_settings(db)

        assert settings.signup_enabled is True
        assert (settings.tileserver_api_key, settings.geocoding_api_key) == (None, None)

    def test_the_tile_source_has_its_key_decrypted(self, db):
        edit_server_settings(
            db,
            tileserver_url="https://tiles.example.org/{z}/{x}/{y}.png",
            map_background_color="#101010",
            tileserver_api_key="tile-key",
        )

        tiles = server_settings_integration.get_tile_server_settings(db)

        assert (tiles.tile_url, tiles.background_color, tiles.api_key) == (
            "https://tiles.example.org/{z}/{x}/{y}.png",
            "#101010",
            "tile-key",
        )

    def test_a_tile_key_that_cannot_be_decrypted_is_a_service_error(self, db):
        db.execute(update(server_settings_models.ServerSettings).values(tileserver_api_key="not-a-token"))

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_integration.get_tile_server_settings(db)

    def test_a_missing_row_leaves_the_tile_source_to_the_callers_defaults(self, db):
        _without_settings_row(db)

        assert (
            server_settings_integration.get_tile_server_settings(db) == server_settings_contracts.TileServerSettings()
        )

    def test_public_links_follow_the_stored_switch(self, db):
        assert server_settings_integration.public_shareable_links_enabled(db) is False

        edit_server_settings(db, public_shareable_links=True)

        assert server_settings_integration.public_shareable_links_enabled(db) is True

    def test_a_broken_install_denies_public_links(self, db):
        _without_settings_row(db)

        assert server_settings_integration.public_shareable_links_enabled(db) is False

    def test_the_notification_retention_is_the_stored_one(self, db):
        edit_server_settings(db, read_notification_retention_days=30)

        assert server_settings_integration.get_read_notification_retention_days(db) == 30


class TestGeocodingConfig:
    def test_the_config_has_the_key_decrypted(self, db):
        edit_server_settings(
            db,
            geocoding_service="photon",
            geocoding_host="photon.example.org",
            geocoding_use_https=False,
            geocoding_rate_limit=2.5,
            geocoding_api_key="geo-key",
        )

        config = server_settings_integration.get_geocoding_config(db)

        assert config == core_geocoding.GeocodingConfig(
            service=core_geocoding.GeocodingService.PHOTON,
            host="photon.example.org",
            use_https=False,
            rate_limit=2.5,
            api_key="geo-key",
        )

    def test_a_missing_row_means_geocoding_is_unavailable(self, db):
        _without_settings_row(db)

        assert server_settings_integration.get_geocoding_config(db) is None

    def test_a_key_that_cannot_be_decrypted_is_a_service_error(self, db):
        db.execute(update(server_settings_models.ServerSettings).values(geocoding_api_key="not-a-token"))

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_integration.get_geocoding_config(db)


class TestPublicSettings:
    def test_the_redirect_addresses_come_from_the_configuration_sorted(self, db, monkeypatch):
        monkeypatch.setattr(
            core_config.settings, "ALLOWED_REDIRECT_URIS", {"https://b.example.org/cb", "https://a.example.org/cb"}
        )

        public = server_settings_service.get_server_settings_for_public(db)

        assert public.allowed_redirect_uris == ["https://a.example.org/cb", "https://b.example.org/cb"]

    def test_the_public_settings_exclude_the_admin_only_ones(self, db):
        public = server_settings_service.get_server_settings_for_public(db).model_dump()

        for admin_only in (
            "signup_require_admin_approval",
            "tileserver_api_key",
            "geocoding_api_key",
            "require_mfa",
            "session_idle_timeout_hours",
            "version",
        ):
            assert admin_only not in public

    def test_a_missing_row_is_a_service_error(self, db):
        _without_settings_row(db)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_service.get_server_settings_for_public(db)


class TestAdminRead:
    def test_the_admin_read_says_whether_the_log_viewer_is_available(self, db, monkeypatch):
        assert server_settings_service.get_server_settings_for_admin(db).logs_viewer_enabled is True

        monkeypatch.setattr(core_config.settings, "ENVIRONMENT", "demo")

        assert server_settings_service.get_server_settings_for_admin(db).logs_viewer_enabled is False


class TestReencryptStoredSecrets:
    @pytest.fixture
    def rotating_keys(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{_NEW_KEY},{_OLD_KEY}")

    @staticmethod
    def _under_old_key(plain: str) -> str:
        return Fernet(_OLD_KEY.encode()).encrypt(plain.encode()).decode()

    def test_a_secret_under_an_older_key_is_rewritten_under_the_first_key_and_still_decrypts(self, db, rotating_keys):
        db.execute(
            update(server_settings_models.ServerSettings).values(
                tileserver_api_key=self._under_old_key("tile-key"), geocoding_api_key=self._under_old_key("geo-key")
            )
        )
        db.execute(update(server_settings_models.MailSettings).values(password=self._under_old_key("s3cret")))

        server_settings_scheduled_jobs.reencrypt_stored_secrets()

        settings = server_settings_crud.get_server_settings(db)
        mail = server_settings_crud.get_mail_settings(db)
        assert settings is not None
        assert mail is not None
        for token, plain in (
            (settings.tileserver_api_key, "tile-key"),
            (settings.geocoding_api_key, "geo-key"),
            (mail.password, "s3cret"),
        ):
            assert token is not None
            assert Fernet(_NEW_KEY.encode()).decrypt(token.encode()) == plain.encode()
            assert core_cryptography.decrypt_token_fernet(token) == plain

    def test_a_secret_no_configured_key_decrypts_is_left_as_it_is(self, db, rotating_keys):
        stranger = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
        db.execute(update(server_settings_models.ServerSettings).values(tileserver_api_key=stranger))

        server_settings_scheduled_jobs.reencrypt_stored_secrets()

        settings = server_settings_crud.get_server_settings(db)
        assert settings is not None
        assert settings.tileserver_api_key == stranger

    def test_nothing_is_rewritten_while_one_key_is_configured(self, db, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", _NEW_KEY)
        edit_server_settings(db, tileserver_api_key="tile-key")
        edit_mail_settings(db, host="smtp.example.org", username="mailer", password="s3cret")
        before = (server_settings_crud.get_server_settings(db), server_settings_crud.get_mail_settings(db))

        server_settings_scheduled_jobs.reencrypt_stored_secrets()

        assert (server_settings_crud.get_server_settings(db), server_settings_crud.get_mail_settings(db)) == before
