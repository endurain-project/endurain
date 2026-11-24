"""The singleton settings rows against the migrated schema: reads, edits, versions, constraints and secret rotation."""

import pytest
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.server_settings.change_utils as server_settings_change_utils
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema
from tests._factories.server_settings import edit_mail_settings, edit_server_settings

_SERVER_SETTINGS = server_settings_models.ServerSettings
_MAIL_SETTINGS = server_settings_models.MailSettings


def _stored_server_settings(db) -> server_settings_schema.ServerSettingsRead:
    stored = server_settings_crud.get_server_settings(db)
    assert stored is not None
    return stored


def _stored_mail_settings(db) -> server_settings_schema.MailSettingsRead:
    stored = server_settings_crud.get_mail_settings(db)
    assert stored is not None
    return stored


class TestSeededRows:
    def test_a_fresh_install_has_the_defaults_the_migrations_seed(self, db):
        stored = _stored_server_settings(db)

        assert (stored.id, stored.version, stored.login_photo_set) == (1, 1, False)
        assert stored.require_mfa == "off"
        assert stored.password_breach_check_enabled is False
        assert stored.signup_sso_enabled is False
        assert stored.session_absolute_timeout_hours == 720
        assert stored.api_key_max_lifetime_days == 365
        assert (stored.tileserver_api_key, stored.geocoding_api_key) == (None, None)

    def test_a_fresh_install_has_mail_switched_off(self, db):
        stored = _stored_mail_settings(db)

        assert (stored.id, stored.version) == (1, 1)
        assert stored.host is None
        assert stored.password is None

    def test_a_second_settings_row_is_refused(self, db):
        with pytest.raises(IntegrityError, match="single_row_check"):
            db.execute(insert(_SERVER_SETTINGS).values(id=2))

    def test_a_second_mail_settings_row_is_refused(self, db):
        with pytest.raises(IntegrityError, match="mail_settings_single_row_check"):
            db.execute(insert(_MAIL_SETTINGS).values(id=2))


class TestConstraints:
    @pytest.mark.parametrize(
        ("column", "value", "constraint"),
        [
            ("require_mfa", "sometimes", "require_mfa_check"),
            ("geocoding_service", "bing", "geocoding_service_check"),
            ("geocoding_rate_limit", 101, "geocoding_rate_limit_check"),
            ("access_token_expire_minutes", 0, "access_token_expire_minutes_check"),
            ("access_token_expire_minutes", 1441, "access_token_expire_minutes_check"),
            ("refresh_token_expire_days", 366, "refresh_token_expire_days_check"),
            ("api_key_max_lifetime_days", 3651, "api_key_max_lifetime_days_check"),
            ("session_idle_timeout_hours", 0, "session_idle_timeout_hours_check"),
            ("session_absolute_timeout_hours", 8761, "session_absolute_timeout_hours_check"),
            ("read_notification_retention_days", 3651, "read_notification_retention_days_check"),
        ],
    )
    def test_the_database_refuses_a_value_out_of_range(self, db, column, value, constraint):
        with pytest.raises(IntegrityError, match=constraint):
            db.execute(update(_SERVER_SETTINGS).values({column: value}))

    def test_the_absolute_timeout_may_not_be_below_the_idle_timeout(self, db):
        with pytest.raises(IntegrityError, match="session_absolute_not_below_idle_check"):
            db.execute(
                update(_SERVER_SETTINGS).values(session_idle_timeout_hours=48, session_absolute_timeout_hours=24)
            )

    def test_the_database_refuses_an_unknown_mail_security(self, db):
        with pytest.raises(IntegrityError, match="mail_settings_security_check"):
            db.execute(update(_MAIL_SETTINGS).values(security="tls13"))


class TestEditServerSettings:
    def test_an_edit_is_read_back_and_bumps_the_version(self, db):
        updated = edit_server_settings(db, num_records_per_page=50, currency="dollar")

        stored = _stored_server_settings(db)
        assert (updated.version, stored.version) == (2, 2)
        assert (stored.num_records_per_page, stored.currency) == (50, "dollar")

    def test_an_omitted_api_key_keeps_the_stored_one(self, db):
        edit_server_settings(db, tileserver_api_key="tile-key")
        stored_token = _stored_server_settings(db).tileserver_api_key
        changes = _stored_server_settings(db).model_dump(exclude={"id", "version", "login_photo_set"})
        del changes["tileserver_api_key"]
        del changes["geocoding_api_key"]

        server_settings_crud.edit_server_settings(
            server_settings_schema.ServerSettingsEdit(**changes | {"num_records_per_page": 75}), db
        )

        stored = _stored_server_settings(db)
        assert stored.num_records_per_page == 75
        assert stored.tileserver_api_key == stored_token
        assert server_settings_change_utils.decrypt_secret(stored.tileserver_api_key, "key") == "tile-key"

    def test_an_edit_without_a_settings_row_is_a_service_error(self, db):
        edit = server_settings_schema.ServerSettingsEdit(
            **_stored_server_settings(db).model_dump(exclude={"id", "version", "login_photo_set"})
        )
        db.execute(delete(_SERVER_SETTINGS))

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_crud.edit_server_settings(edit, db)

    def test_reading_without_a_settings_row_finds_nothing(self, db):
        db.execute(delete(_SERVER_SETTINGS))

        assert server_settings_crud.get_server_settings(db) is None


class TestSetLoginPhoto:
    def test_setting_the_photo_bumps_the_version_and_reports_there_was_none(self, db):
        version, had_photo = server_settings_crud.set_login_photo(True, db)

        assert (version, had_photo) == (2, False)
        assert _stored_server_settings(db).login_photo_set is True

    def test_setting_it_again_bumps_the_version_and_reports_the_photo_it_replaced(self, db):
        server_settings_crud.set_login_photo(True, db)

        version, had_photo = server_settings_crud.set_login_photo(True, db)

        assert (version, had_photo) == (3, True)

    def test_removing_the_photo_clears_the_flag(self, db):
        server_settings_crud.set_login_photo(True, db)

        version, had_photo = server_settings_crud.set_login_photo(False, db)

        assert (version, had_photo) == (3, True)
        assert _stored_server_settings(db).login_photo_set is False

    def test_a_missing_settings_row_is_a_service_error(self, db):
        db.execute(delete(_SERVER_SETTINGS))

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_crud.set_login_photo(True, db)


class TestMailSettings:
    def test_an_edit_is_read_back_with_the_password_kept_encrypted(self, db):
        updated = edit_mail_settings(db, host="smtp.example.org", username="mailer", password="s3cret")

        stored = _stored_mail_settings(db)
        assert updated.version == stored.version == 2
        assert stored.host == "smtp.example.org"
        assert stored.password not in (None, "s3cret")
        assert server_settings_change_utils.decrypt_secret(stored.password, "password") == "s3cret"

    def test_an_omitted_password_keeps_the_stored_one(self, db):
        edit_mail_settings(db, host="smtp.example.org", password="s3cret")
        stored_token = _stored_mail_settings(db).password

        server_settings_crud.edit_mail_settings(
            server_settings_schema.MailSettingsEdit(
                host="other.example.org", port=465, security="ssl", username=None, from_address=None
            ),
            db,
        )

        stored = _stored_mail_settings(db)
        assert (stored.host, stored.port, stored.security) == ("other.example.org", 465, "ssl")
        assert stored.password == stored_token

    def test_a_missing_row_reads_as_none_and_cannot_be_edited(self, db):
        edit = server_settings_schema.MailSettingsEdit(
            host=None, port=587, security="starttls", username=None, from_address=None
        )
        db.execute(delete(_MAIL_SETTINGS))

        assert server_settings_crud.get_mail_settings(db) is None
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_crud.edit_mail_settings(edit, db)

    def test_a_locking_read_returns_the_row_as_a_plain_read_does(self, db):
        assert server_settings_crud.get_mail_settings(db, for_update=True) == server_settings_crud.get_mail_settings(db)
        assert server_settings_crud.get_server_settings(db, for_update=True) == _stored_server_settings(db)


class TestReencryptBatches:
    def test_a_batch_reports_the_last_row_it_read_and_rewrites_nothing_under_the_primary_key(self, db):
        edit_server_settings(db, tileserver_api_key="tile-key", geocoding_api_key="geo-key")
        edit_mail_settings(db, host="smtp.example.org", password="s3cret")

        settings_batch = server_settings_crud.stage_reencrypt_batch_settings(None, 10, db)
        mail_batch = server_settings_crud.stage_reencrypt_batch_mail(None, 10, db)

        assert (settings_batch.last_id, settings_batch.counts.rotated) == (1, 0)
        assert (mail_batch.last_id, mail_batch.counts.rotated) == (1, 0)
        assert server_settings_crud.stage_reencrypt_batch_settings(1, 10, db).last_id is None
