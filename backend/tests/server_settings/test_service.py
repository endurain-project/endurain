"""Tests for the server-settings write path.

The service is where the tile-URL network policy is enforced: the schema is also
what deserializes settings on every *read*, so a validator there would put a DNS
lookup on the read path of the whole app.
"""

import io
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import jasil.testing as jasil_testing
import pytest
from fastapi import UploadFile

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.geocoding as core_geocoding
import core.mail as core_mail
import core.network as core_network
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.schema as auth_schema
import modules.server_settings.audit_actions as server_settings_audit_actions
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.login_photo_service as server_settings_login_photo_service
import modules.server_settings.mail_service as server_settings_mail_service
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service
from tests._helpers import images


def _stored(**overrides) -> server_settings_schema.ServerSettingsRead:
    """Settings as the crud layer returns them (the tile API key still encrypted)."""
    values = dict(
        id=1,
        version=1,
        units="metric",
        public_shareable_links=False,
        public_shareable_links_user_info=False,
        login_photo_set=False,
        currency="euro",
        num_records_per_page=25,
        signup_enabled=False,
        signup_require_admin_approval=True,
        signup_require_email_verification=True,
        password_breach_check_enabled=False,
        require_mfa="off",
        signup_sso_enabled=False,
        sso_enabled=False,
        local_login_enabled=True,
        sso_auto_redirect=False,
        tileserver_url="https://tiles.example.com/{z}/{x}/{y}.png",
        tileserver_attribution="Test",
        map_background_color="#dddddd",
        tileserver_regenerate_thumbnails_on_change=False,
        password_length_regular_users=8,
        password_length_admin_users=12,
        tileserver_api_key="enc-old",
        geocoding_service="nominatim",
        geocoding_host=None,
        geocoding_use_https=True,
        geocoding_rate_limit=1.0,
        session_idle_timeout_enabled=False,
        session_idle_timeout_hours=1,
        session_absolute_timeout_hours=24,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        api_key_max_lifetime_days=365,
        read_notification_retention_days=90,
        geocoding_api_key=None,
    )
    values.update(overrides)
    return server_settings_schema.ServerSettingsRead(**values)


def _full_edit(stored: server_settings_schema.ServerSettingsRead, **overrides):
    """The whole record, the way the frontend sends it on every save (key in plain text)."""
    body = stored.model_dump(exclude={"id", "login_photo_set", "version"})
    body["tileserver_api_key"] = "plain-old"
    body.update(overrides)
    return server_settings_schema.ServerSettingsEdit(**body)


_PNG = images.png_with_text()
VERIFIER = MagicMock()


@pytest.fixture
def edit_env():
    """Patch the collaborators of edit_server_settings and expose them."""
    stored = _stored()
    with (
        patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored),
        patch.object(
            server_settings_service.server_settings_crud,
            "edit_server_settings",
            side_effect=lambda attrs, db: stored.model_copy(update=attrs.model_dump(exclude_unset=True)),
        ) as write,
        patch.object(server_settings_service.server_settings_publishers, "publish_tile_settings_changed") as publish,
        patch.object(core_network, "url_rejection_reason_bounded", return_value=None) as dns,
        patch.object(
            core_cryptography,
            "decrypt_token_fernet",
            side_effect=lambda token: {"enc-old": "plain-old", "enc-new": "plain-new"}[token],
        ),
        patch.object(core_cryptography, "encrypt_token_fernet", return_value="enc-new"),
    ):
        yield MagicMock(stored=stored, write=write, publish=publish, dns=dns)


class TestTileServerUrlIsCheckedOnWrite:
    def test_a_url_targeting_a_non_public_address_is_refused(self, edit_env):
        """The renderer refuses it too, but only later, in a background job.

        By then the admin has seen no error and the bad value is already stored.
        """
        db = MagicMock()
        edit_env.dns.return_value = "URL resolves to a non-public address"

        with pytest.raises(core_exceptions.InvalidInputError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://internal.example.com/{z}/{x}/{y}.png"),
                None,
                VERIFIER,
                db,
                if_match="*",
            )

        edit_env.write.assert_not_called()
        # The only commit is the one that spends the step-up; the refused settings are never written.
        db.commit.assert_called_once()

    def test_the_placeholders_are_filled_before_the_check(self, edit_env):
        """``{z}/{x}/{y}`` is not a parseable URL; the host is what matters."""
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_url="https://other.example.com/{z}/{x}/{y}.png"),
            None,
            VERIFIER,
            MagicMock(),
            if_match="*",
        )

        assert edit_env.dns.call_args.args[0] == "https://other.example.com/0/0/0.png"

    @pytest.mark.parametrize(
        "template", [t["url_template"] for t in server_settings_constants.TILE_MAPS_TEMPLATES.values()]
    )
    def test_every_builtin_template_can_be_saved(self, edit_env, template):
        """``{r}`` (Stadia retina) is dropped by the renderer, so it must not be a 400."""
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_url=template), None, VERIFIER, MagicMock(), if_match="*"
        )

        assert "{" not in edit_env.dns.call_args.args[0]

    def test_an_unfillable_placeholder_is_a_400_not_a_background_500(self, edit_env):
        """The renderer resolves the same template before every tile fetch."""
        with pytest.raises(core_exceptions.InvalidInputError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://tiles.example.com/{}/{z}/{x}/{y}.png"),
                None,
                VERIFIER,
                MagicMock(),
                if_match="*",
            )

        edit_env.write.assert_not_called()


_SECURITY_CHANGES = {
    "signup_enabled": True,
    "sso_enabled": True,
    "local_login_enabled": False,
    "sso_auto_redirect": True,
    "signup_sso_enabled": True,
    "signup_require_admin_approval": False,
    "signup_require_email_verification": False,
    "password_breach_check_enabled": True,
    "require_mfa": "administrators",
    "password_length_regular_users": 10,
    "password_length_admin_users": 14,
    "session_idle_timeout_enabled": True,
    "session_idle_timeout_hours": 2,
    "session_absolute_timeout_hours": 48,
    "access_token_expire_minutes": 30,
    "refresh_token_expire_days": 14,
    "api_key_max_lifetime_days": 30,
    "public_shareable_links_user_info": True,
    "geocoding_service": "photon",
    "geocoding_host": "nominatim.example.com",
    "geocoding_use_https": False,
    "tileserver_url": "https://other.example.com/{z}/{x}/{y}.png",
}


class TestSecurityFieldsNeedStepUp:
    """A change to a field governing sign-in, sessions, public links or the server's outbound requests needs step-up."""

    def test_every_security_field_is_covered_by_a_case(self):
        assert set(_SECURITY_CHANGES) == server_settings_constants.SECURITY_FIELDS

    @pytest.mark.parametrize(("field", "value"), _SECURITY_CHANGES.items())
    def test_a_changed_security_field_without_a_step_up_is_refused_before_any_write(self, edit_env, field, value):
        verifier = MagicMock(side_effect=core_exceptions.StepUpFailedError())
        db = MagicMock()

        with pytest.raises(core_exceptions.StepUpFailedError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, **{field: value}), None, verifier, db, if_match="*"
            )

        verifier.assert_called_once_with(
            auth_schema.StepUpVerification(), idp_constants.StepUpAction.ADMIN_SERVER_SETTINGS_EDIT
        )
        edit_env.write.assert_not_called()
        db.commit.assert_not_called()

    def test_the_step_up_is_committed_before_the_dns_lookup(self, edit_env):
        # A step-up stages the consumption of a backup code and its audit row; a rollback would let the code be reused.
        calls = []
        db = MagicMock()
        db.rollback.side_effect = lambda: calls.append("rollback")
        db.commit.side_effect = lambda: calls.append("commit")
        verifier = MagicMock(side_effect=lambda *_: calls.append("step_up"))
        edit_env.dns.side_effect = lambda *_, **__: calls.append("dns")

        server_settings_service.edit_server_settings(
            _full_edit(
                edit_env.stored, signup_enabled=True, tileserver_url="https://other.example.com/{z}/{x}/{y}.png"
            ),
            auth_schema.StepUpVerification(current_password="admin-password"),
            verifier,
            db,
            if_match="*",
        )

        assert calls[:3] == ["step_up", "commit", "dns"]

    def test_without_a_step_up_the_read_transaction_is_rolled_back_before_the_dns_lookup(self, edit_env):
        calls = []
        db = MagicMock()
        db.rollback.side_effect = lambda: calls.append("rollback")
        db.commit.side_effect = lambda: calls.append("commit")
        edit_env.dns.side_effect = lambda *_, **__: calls.append("dns")

        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, geocoding_rate_limit=2.0, currency="dollar"),
            None,
            MagicMock(),
            db,
            if_match="*",
        )

        assert calls[:2] == ["rollback", "dns"]

    @pytest.mark.parametrize(("field", "value"), _SECURITY_CHANGES.items())
    def test_a_changed_security_field_with_a_step_up_is_saved(self, edit_env, field, value):
        verifier = MagicMock()
        step_up = auth_schema.StepUpVerification(current_password="admin-password")

        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, **{field: value}), step_up, verifier, MagicMock(), if_match="*"
        )

        verifier.assert_called_once_with(step_up, idp_constants.StepUpAction.ADMIN_SERVER_SETTINGS_EDIT)
        edit_env.write.assert_called_once()

    def test_a_non_security_change_needs_no_step_up(self, edit_env):
        verifier = MagicMock()

        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar", num_records_per_page=50),
            None,
            verifier,
            MagicMock(),
            if_match="*",
        )

        verifier.assert_not_called()
        edit_env.write.assert_called_once()

    def test_resending_the_unchanged_security_values_needs_no_step_up(self, edit_env):
        verifier = MagicMock()

        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar", access_token_expire_minutes=15),
            None,
            verifier,
            MagicMock(),
            if_match="*",
        )

        verifier.assert_not_called()

    def test_a_stale_tag_is_refused_before_the_step_up_is_checked(self, edit_env):
        verifier = MagicMock()

        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, signup_enabled=True), None, verifier, MagicMock(), if_match='"99"'
            )

        verifier.assert_not_called()


class TestOnlyRealChangesCount:
    def test_resending_the_unchanged_record_does_nothing(self, edit_env):
        """The frontend sends every field on every save; that must not look like a tile change."""
        db = MagicMock()

        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored), None, VERIFIER, db, if_match="*"
        )

        edit_env.dns.assert_not_called()
        edit_env.write.assert_not_called()
        edit_env.publish.assert_not_called()
        db.commit.assert_not_called()
        assert result.tileserver_api_key_set is True
        assert not hasattr(result, "tileserver_api_key")

    def test_a_non_tile_change_commits_without_publishing(self, edit_env):
        db = MagicMock()

        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar"), None, VERIFIER, db, if_match="*"
        )

        edit_env.dns.assert_not_called()
        edit_env.publish.assert_not_called()
        db.commit.assert_called_once()

    def test_a_tile_change_publishes_only_the_changed_map_fields(self, edit_env):
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, map_background_color="#000000"), None, VERIFIER, MagicMock(), if_match="*"
        )

        assert edit_env.publish.call_args.args[0] == {"map_background_color"}
        edit_env.dns.assert_not_called()

    def test_an_unchanged_api_key_keeps_its_stored_token(self, edit_env):
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar"), None, VERIFIER, MagicMock(), if_match="*"
        )

        written = edit_env.write.call_args.args[0]
        assert written.tileserver_api_key == "enc-old"

    def test_a_changed_api_key_is_encrypted_and_never_returned(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_api_key="plain-new"), None, VERIFIER, MagicMock(), if_match="*"
        )

        assert edit_env.write.call_args.args[0].tileserver_api_key == "enc-new"
        assert result.tileserver_api_key_set is True
        assert "plain-new" not in result.model_dump_json()
        assert edit_env.publish.call_args.args[0] == {"tileserver_api_key"}

    def test_clearing_the_api_key_stores_none(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_api_key=None), None, VERIFIER, MagicMock(), if_match="*"
        )

        assert edit_env.write.call_args.args[0].tileserver_api_key is None
        assert result.tileserver_api_key_set is False

    def test_an_undecryptable_stored_key_can_be_replaced(self, edit_env):
        """After the encryption key changes, re-entering the key must still work."""
        with patch.object(
            core_cryptography,
            "decrypt_token_fernet",
            side_effect=core_exceptions.UndecryptableError(),
        ):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_api_key="plain-new"), None, VERIFIER, MagicMock(), if_match="*"
            )

        assert edit_env.write.call_args.args[0].tileserver_api_key == "enc-new"

    def test_the_row_is_locked_for_the_edit(self, edit_env):
        db = MagicMock()
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=edit_env.stored
        ) as read:
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, currency="dollar"), None, VERIFIER, db, if_match="*"
            )

        assert [call.kwargs for call in read.call_args_list] == [{"for_update": False}, {"for_update": True}]

    def test_the_dns_check_runs_before_the_row_is_locked(self, edit_env):
        """A slow resolver must not hold the settings lock."""
        order = []
        edit_env.dns.side_effect = lambda *a, **k: order.append("dns")

        def read(db, for_update=False):
            order.append("lock" if for_update else "read")
            return edit_env.stored

        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", side_effect=read):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://other.example.com/{z}/{x}/{y}.png"),
                None,
                VERIFIER,
                MagicMock(),
                if_match="*",
            )

        assert order == ["read", "dns", "lock"]

    def test_a_stale_if_match_is_refused_and_writes_nothing(self, edit_env):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, currency="dollar"), None, VERIFIER, MagicMock(), if_match='"99"'
            )

        edit_env.write.assert_not_called()

    def test_the_current_if_match_is_accepted(self, edit_env):
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar"), None, VERIFIER, MagicMock(), if_match='"1"'
        )

        edit_env.write.assert_called_once()


class TestGeocodingSettingsOnWrite:
    @pytest.fixture
    def geo_env(self, edit_env):
        with patch.object(core_network, "url_rejection_reason_bounded", return_value=None) as dns:
            edit_env.geo_dns = dns
            yield edit_env

    def test_a_save_that_leaves_geocoding_alone_does_no_lookup(self, geo_env):
        geo_env.geo_dns.reset_mock()

        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, currency="dollar"), None, VERIFIER, MagicMock(), if_match="*"
        )

        geo_env.geo_dns.assert_not_called()

    def test_the_default_host_is_checked_when_none_is_set(self, geo_env):
        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_service="photon"), None, VERIFIER, MagicMock(), if_match="*"
        )

        assert geo_env.geo_dns.call_args.args[0] == "https://photon.komoot.io/reverse"

    def test_a_custom_host_and_scheme_are_checked(self, geo_env):
        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_host="nominatim.lan:8080", geocoding_use_https=False),
            None,
            VERIFIER,
            MagicMock(),
            if_match="*",
        )

        assert geo_env.geo_dns.call_args.args[0] == "http://nominatim.lan:8080/reverse"

    def test_a_refused_host_is_a_400_and_writes_nothing(self, geo_env):
        geo_env.geo_dns.return_value = "URL resolves to a private address"

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            server_settings_service.edit_server_settings(
                _full_edit(geo_env.stored, geocoding_host="10.0.0.5"), None, VERIFIER, MagicMock(), if_match="*"
            )

        assert "SSRF_ALLOWED_HOSTS" in exc_info.value.detail
        geo_env.write.assert_not_called()

    def test_geocode_without_a_key_is_refused(self, geo_env):
        body = _full_edit(geo_env.stored, geocoding_service="geocode")
        body = body.model_copy(update={"geocoding_api_key": None})

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            server_settings_service.edit_server_settings(body, None, VERIFIER, MagicMock(), if_match="*")

        assert "API key" in exc_info.value.detail
        geo_env.geo_dns.assert_not_called()

    def test_geocode_with_a_new_key_is_accepted_and_the_key_encrypted(self, geo_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_service="geocode", geocoding_api_key="plain-new"),
            None,
            VERIFIER,
            MagicMock(),
            if_match="*",
        )

        assert geo_env.write.call_args.args[0].geocoding_api_key == "enc-new"
        assert result.geocoding_api_key_set is True
        assert "plain-new" not in result.model_dump_json()

    def test_geocode_with_a_stored_key_and_none_sent_is_accepted(self, geo_env):
        geo_env.stored = geo_env.stored.model_copy(update={"geocoding_api_key": "enc-old"})
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=geo_env.stored
        ):
            server_settings_service.edit_server_settings(
                _full_edit(geo_env.stored, geocoding_service="geocode"), None, VERIFIER, MagicMock(), if_match="*"
            )

        geo_env.write.assert_called_once()

    def test_the_two_keys_are_independent(self, geo_env):
        server_settings_service.edit_server_settings(
            _full_edit(geo_env.stored, geocoding_api_key="plain-new"), None, VERIFIER, MagicMock(), if_match="*"
        )

        written = geo_env.write.call_args.args[0]
        assert written.geocoding_api_key == "enc-new"
        assert written.tileserver_api_key == "enc-old"


class TestAdminReadStepUpFields:
    def test_the_admin_read_lists_the_settings_that_need_the_step_up(self):
        result = server_settings_service._to_admin_read(_stored())

        assert result.step_up_fields == sorted(server_settings_constants.SECURITY_FIELDS)

    def test_the_saved_settings_list_them_too(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, currency="dollar"), None, VERIFIER, MagicMock(), if_match="*"
        )

        assert result.step_up_fields == sorted(server_settings_constants.SECURITY_FIELDS)


class TestAdminReadLogsViewer:
    @pytest.mark.parametrize("enabled", [True, False])
    def test_the_admin_read_says_whether_the_log_viewer_is_available(self, enabled):
        with patch("core.config.Settings.logs_viewer_enabled", enabled):
            result = server_settings_service._to_admin_read(_stored())

        assert result.logs_viewer_enabled is enabled


class TestGetGeocodingConfig:
    def test_decrypts_the_key(self, edit_env):
        stored = edit_env.stored.model_copy(update={"geocoding_api_key": "enc-old", "geocoding_host": "h.example.com"})
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored):
            config = server_settings_service.get_geocoding_config(MagicMock())

        assert config.api_key == "plain-old"
        assert config.host == "h.example.com"
        assert config.service == core_geocoding.GeocodingService.NOMINATIM

    def test_a_missing_row_means_geocoding_is_unavailable(self):
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=None):
            assert server_settings_service.get_geocoding_config(MagicMock()) is None


class TestGetSessionPolicy:
    def test_timeouts_enabled(self, edit_env):
        stored = edit_env.stored.model_copy(
            update={
                "session_idle_timeout_enabled": True,
                "session_idle_timeout_hours": 2,
                "session_absolute_timeout_hours": 48,
                "access_token_expire_minutes": 30,
                "refresh_token_expire_days": 14,
                "api_key_max_lifetime_days": 90,
            }
        )
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored):
            policy = server_settings_service.get_session_policy(MagicMock())

        assert policy.access_token_ttl == timedelta(minutes=30)
        assert policy.refresh_token_ttl == timedelta(days=14)
        assert policy.idle_timeout == timedelta(hours=2)
        assert policy.absolute_timeout == timedelta(hours=48)
        assert policy.api_key_max_lifetime == timedelta(days=90)

    def test_disabled_idle_timeout_is_none_but_absolute_timeout_and_lifetimes_stay(self, edit_env):
        policy = server_settings_service.get_session_policy(MagicMock())

        assert policy.idle_timeout is None
        assert policy.absolute_timeout == timedelta(hours=edit_env.stored.session_absolute_timeout_hours)
        assert policy.access_token_ttl == timedelta(minutes=15)
        assert policy.refresh_token_ttl == timedelta(days=7)
        assert policy.api_key_max_lifetime == timedelta(days=365)

    def test_a_missing_row_raises(self):
        with (
            patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=None),
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            server_settings_service.get_session_policy(MagicMock())


class TestRetention:
    def test_the_stored_value_is_returned_by_the_integration_read(self, edit_env):
        from modules.server_settings import integration_service

        stored = edit_env.stored.model_copy(update={"read_notification_retention_days": 30})
        with patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=stored):
            assert integration_service.get_read_notification_retention_days(MagicMock()) == 30


class TestLoginPhoto:
    def test_upload_writes_the_blob_before_committing_the_flag(self):
        calls = []
        storage = MagicMock()
        storage.save.side_effect = lambda *a: calls.append("save")
        db = MagicMock()
        db.commit.side_effect = lambda: calls.append("commit")
        file = MagicMock(content_type="text/plain")

        with (
            patch.object(core_file_uploads, "read_validated_upload_sync", return_value=_PNG),
            patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)),
        ):
            photo = server_settings_login_photo_service.upload_login_photo(file, storage, db)

        assert photo == (server_settings_schema.LoginPhotoRead(version=4), False)
        assert calls == ["save", "commit"]
        # The type is detected from the bytes, not taken from the client's claim.
        area, key, data, content_type = storage.save.call_args.args
        assert (area, key, content_type) == ("server_images", "login.png", "image/png")
        assert not images.has_metadata(data)

    def test_upload_rejects_a_photo_over_the_login_cap(self):
        big = _PNG + b"0" * server_settings_constants.LOGIN_PHOTO_MAX_BYTES
        storage = MagicMock()

        with (
            patch.object(core_file_uploads, "read_validated_upload_sync", return_value=big),
            pytest.raises(core_exceptions.PayloadTooLargeError),
        ):
            server_settings_login_photo_service.upload_login_photo(MagicMock(), storage, MagicMock())

        storage.save.assert_not_called()

    def test_upload_rejects_an_unrecognised_format(self):
        storage = MagicMock()

        with (
            patch.object(core_file_uploads, "read_validated_upload_sync", return_value=b"not an image"),
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            server_settings_login_photo_service.upload_login_photo(MagicMock(), storage, MagicMock())

        storage.save.assert_not_called()

    def test_delete_clears_the_flag_before_removing_the_blob(self):
        calls = []
        storage = MagicMock()
        storage.delete.side_effect = lambda *a: calls.append("delete")
        db = MagicMock()
        db.commit.side_effect = lambda: calls.append("commit")

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)):
            server_settings_login_photo_service.delete_login_photo(storage, db)

        assert calls == ["commit", "delete"]
        storage.delete.assert_called_once_with("server_images", "login.png")

    def test_delete_survives_a_storage_failure(self):
        storage = MagicMock()
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("storage down")
        db = MagicMock()

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)):
            server_settings_login_photo_service.delete_login_photo(storage, db)

        db.commit.assert_called_once()

    def test_delete_propagates_an_unexpected_storage_error(self):
        storage = MagicMock()
        storage.delete.side_effect = TypeError("bug")

        with (
            patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)),
            pytest.raises(TypeError),
        ):
            server_settings_login_photo_service.delete_login_photo(storage, MagicMock())

    def test_version_is_none_when_no_photo_is_set(self):
        with patch.object(
            server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=False, version=5)
        ):
            assert server_settings_login_photo_service.get_login_photo_version(MagicMock()) is None

    def test_version_is_the_settings_version_when_a_photo_is_set(self):
        with patch.object(
            server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=True, version=5)
        ):
            assert server_settings_login_photo_service.get_login_photo_version(MagicMock()) == 5

    def test_read_returns_none_when_missing(self):
        storage = MagicMock()
        storage.get.return_value = None

        assert server_settings_login_photo_service.read_login_photo(storage) is None

    @pytest.mark.parametrize(
        "data,media_type",
        [(_PNG, "image/png"), (b"\xff\xd8\xff\xe0", "image/jpeg"), (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp")],
    )
    def test_read_returns_the_detected_type(self, data, media_type):
        storage = MagicMock()
        storage.get.return_value = data

        assert server_settings_login_photo_service.read_login_photo(storage) == (data, media_type)


def _mail_row(**overrides) -> server_settings_schema.MailSettingsRead:
    """Mail settings as the crud layer returns them (the password still encrypted)."""
    values = dict(
        id=1,
        host="mail.example.com",
        port=587,
        security="starttls",
        username="me@example.com",
        from_address=None,
        password="enc-old",
    )
    values.update(overrides)
    return server_settings_schema.MailSettingsRead(**values)


def _mail_edit(stored: server_settings_schema.MailSettingsRead, **overrides):
    """The whole mail record, the way the frontend sends it (password omitted unless given)."""
    body = stored.model_dump(exclude={"id", "password", "version"})
    body.update(overrides)
    return server_settings_schema.MailSettingsEdit(**body)


_STEP_UP = auth_schema.StepUpVerification(current_password="admin-password")
_VERIFY = MagicMock()


@pytest.fixture
def mail_env():
    """Patch the collaborators of the mail service functions and expose them."""
    stored = _mail_row()
    with (
        patch.object(server_settings_service.server_settings_crud, "get_mail_settings", return_value=stored) as read,
        patch.object(
            server_settings_service.server_settings_crud,
            "edit_mail_settings",
            side_effect=lambda attrs, db: stored.model_copy(update=attrs.model_dump(exclude_unset=True)),
        ) as write,
        patch.object(core_mail, "mail_problems", return_value=[]) as problems,
        patch.object(
            core_cryptography,
            "decrypt_token_fernet",
            side_effect=lambda token: {"enc-old": "plain-old", "enc-new": "plain-new"}[token],
        ),
        patch.object(core_cryptography, "encrypt_token_fernet", return_value="enc-new"),
    ):
        yield MagicMock(stored=stored, read=read, write=write, problems=problems)


class TestEditMailSettings:
    def test_resending_the_unchanged_record_does_nothing(self, mail_env):
        db = MagicMock()

        result = server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored), _STEP_UP, _VERIFY, db, if_match="*"
        )

        mail_env.write.assert_not_called()
        db.commit.assert_called_once()
        db.rollback.assert_called_once()
        assert result.host == "mail.example.com"

    def test_the_step_up_is_committed_before_the_mail_check(self, mail_env):
        # A step-up stages the consumption of a backup code and its audit row; a rollback would let the code be reused.
        calls = []
        db = MagicMock()
        db.rollback.side_effect = lambda: calls.append("rollback")
        db.commit.side_effect = lambda: calls.append("commit")
        verifier = MagicMock(side_effect=lambda *_: calls.append("step_up"))
        mail_env.problems.side_effect = lambda *_: calls.append("check") or []

        server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, port=465), _STEP_UP, verifier, db, if_match="*"
        )

        assert calls[:3] == ["step_up", "commit", "check"]

    def test_the_row_is_locked_for_the_edit(self, mail_env):
        server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
        )

        assert mail_env.read.call_args.kwargs == {"for_update": True}

    def test_a_stale_if_match_is_refused_and_writes_nothing(self, mail_env):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match='"9"'
            )

        mail_env.write.assert_not_called()

    def test_an_omitted_password_keeps_the_stored_token(self, mail_env):
        db = MagicMock()

        server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, db, if_match="*"
        )

        assert "password" not in mail_env.write.call_args.args[0].model_fields_set
        # The step-up is committed, then the write.
        assert db.commit.call_count == 2

    def test_an_unchanged_password_keeps_its_stored_token(self, mail_env):
        body = _mail_edit(mail_env.stored, port=465, password="plain-old")

        server_settings_mail_service.edit_mail_settings(body, _STEP_UP, _VERIFY, MagicMock(), if_match="*")

        assert mail_env.write.call_args.args[0].password == "enc-old"

    @pytest.mark.parametrize("cleared", [None, ""])
    def test_clearing_the_password_stores_none(self, mail_env, cleared):
        result = server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, password=cleared), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
        )

        assert mail_env.write.call_args.args[0].password is None
        assert result.password_set is False

    def test_a_changed_password_is_encrypted_and_never_returned(self, mail_env):
        result = server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, password="plain-new"), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
        )

        assert mail_env.write.call_args.args[0].password == "enc-new"
        assert result.password_set is True
        assert "plain-new" not in result.model_dump_json()
        assert "enc-new" not in result.model_dump_json()

    def test_an_invalid_configuration_is_a_400_and_writes_nothing(self, mail_env):
        mail_env.problems.return_value = [
            "Port must be between 1 and 65535",
            "Username and password must be set together",
        ]

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
            )

        assert "Port must be between" in exc_info.value.detail
        assert "; " in exc_info.value.detail
        mail_env.write.assert_not_called()

    def test_disabling_mail_skips_validation(self, mail_env):
        mail_env.problems.return_value = ["never shown"]

        result = server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, host=None), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
        )

        mail_env.problems.assert_not_called()
        assert result.host is None

    def test_the_password_is_checked_in_plain_text(self, mail_env):
        server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
        )

        config = mail_env.problems.call_args.args[0]
        assert config.password == "plain-old"
        assert config.from_address == "me@example.com"


class TestMailConfig:
    def test_decrypts_the_password_and_falls_back_to_the_username_sender(self, mail_env):
        config = server_settings_mail_service.get_mail_config(MagicMock())

        assert config.password == "plain-old"
        assert config.from_address == "me@example.com"
        assert config.security == core_mail.MailSecurity.STARTTLS

    def test_an_explicit_sender_wins(self, mail_env):
        mail_env.read.return_value = _mail_row(from_address="noreply@example.com")

        assert server_settings_mail_service.get_mail_config(MagicMock()).from_address == "noreply@example.com"

    def test_no_host_means_mail_is_disabled(self, mail_env):
        mail_env.read.return_value = _mail_row(host=None)

        assert server_settings_mail_service.get_mail_config(MagicMock()) is None

    def test_a_missing_row_means_mail_is_disabled(self, mail_env):
        mail_env.read.return_value = None

        assert server_settings_mail_service.get_mail_config(MagicMock()) is None


class TestEmailStatus:
    """Test suite for the email status the admin mail settings read carries."""

    def test_configured(self, mail_env):
        result = server_settings_mail_service.get_mail_settings_for_admin(MagicMock()).email_status

        assert result.configured is True
        assert result.problems == []

    def test_unset_host_reports_missing_host(self, mail_env):
        mail_env.read.return_value = _mail_row(host=None)

        result = server_settings_mail_service.get_mail_settings_for_admin(MagicMock()).email_status

        assert result.configured is False
        assert result.problems == ["Host is not set"]

    def test_invalid_settings_report_problems(self, mail_env):
        mail_env.problems.return_value = ["Username and password must be set together"]

        result = server_settings_mail_service.get_mail_settings_for_admin(MagicMock()).email_status

        assert result.configured is False
        assert result.problems == ["Username and password must be set together"]

    def test_an_undecryptable_password_does_not_block_the_read(self, mail_env):
        with patch.object(
            core_cryptography, "decrypt_token_fernet", side_effect=core_exceptions.CryptographyError("x")
        ):
            result = server_settings_mail_service.get_mail_settings_for_admin(MagicMock())

        assert result.email_status.configured is False
        assert result.email_status.problems == [
            "The stored SMTP password cannot be decrypted; enter it again in the server settings"
        ]
        assert result.password_set is True

    def test_an_edit_returns_the_status_of_the_saved_settings(self, mail_env):
        mail_env.problems.side_effect = [[], ["Username and password must be set together"]]

        result = server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
        )

        assert result.email_status.problems == ["Username and password must be set together"]


_ADMIN_ID = uuid.UUID(int=7)


class TestSendTestEmail:
    """Test suite for send_test_email."""

    @staticmethod
    def _admin():
        return MagicMock(email="admin@example.com", preferred_language="en", **{"name": "Admin"})

    @pytest.fixture(autouse=True)
    def _lookup(self):
        with patch(
            "modules.server_settings.mail_service.users_integration.get_user", return_value=self._admin()
        ) as get:
            self.get_user = get
            yield

    def test_an_admin_who_no_longer_exists_raises_404(self, mail_env):
        self.get_user.return_value = None
        mail = MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            server_settings_mail_service.send_test_email(_ADMIN_ID, mail, MagicMock())

        mail.send.assert_not_called()

    def test_not_configured_raises_503_with_reasons(self, mail_env):
        mail_env.read.return_value = _mail_row(host=None)
        mail = MagicMock()

        with pytest.raises(core_exceptions.ServiceUnavailableError) as exc_info:
            server_settings_mail_service.send_test_email(_ADMIN_ID, mail, MagicMock())

        assert "Host is not set" in exc_info.value.detail
        mail.send.assert_not_called()

    @patch("modules.server_settings.service.core_config.settings")
    def test_sends_to_the_admin_only(self, mock_settings, mail_env):
        mock_settings.ENDURAIN_HOST = "https://endurain.example.com"
        mail = MagicMock()

        server_settings_mail_service.send_test_email(_ADMIN_ID, mail, MagicMock())

        message = mail.send.call_args.args[0]
        assert message.to == ["admin@example.com"]
        assert "mail.example.com:587" in message.text
        assert message.html and message.text

    @patch("modules.server_settings.service.core_config.settings")
    def test_mail_error_becomes_502_with_status_code(self, mock_settings, mail_env):
        mock_settings.ENDURAIN_HOST = "https://endurain.example.com"
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("SMTP authentication failed (status 535)", status=535)

        with pytest.raises(core_exceptions.UpstreamError) as exc_info:
            server_settings_mail_service.send_test_email(_ADMIN_ID, mail, MagicMock())

        assert "status 535" in exc_info.value.detail


class TestGetServerSettingsForPublic:
    """Test suite for get_server_settings_for_public."""

    @staticmethod
    def _stored_settings() -> server_settings_schema.ServerSettingsRead:
        return server_settings_schema.ServerSettingsRead(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            signup_require_admin_approval=True,
            signup_require_email_verification=True,
            password_breach_check_enabled=False,
            require_mfa="off",
            signup_sso_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            tileserver_regenerate_thumbnails_on_change=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
            tileserver_api_key="encrypted",
            geocoding_service="nominatim",
            geocoding_host=None,
            geocoding_use_https=True,
            geocoding_rate_limit=1.0,
            session_idle_timeout_enabled=False,
            session_idle_timeout_hours=1,
            session_absolute_timeout_hours=24,
            access_token_expire_minutes=15,
            refresh_token_expire_days=7,
            api_key_max_lifetime_days=365,
            read_notification_retention_days=90,
            geocoding_api_key="encrypted-geo",
        )

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_reflects_configured_uris_sorted(self, mock_get, mock_config, mock_db):
        """Test the redirect addresses mirror ALLOWED_REDIRECT_URIS, sorted."""
        mock_get.return_value = self._stored_settings()
        mock_config.ALLOWED_REDIRECT_URIS = {"gadgetbridge://auth", "endurain://cb"}

        result = server_settings_service.get_server_settings_for_public(mock_db)

        assert result.allowed_redirect_uris == ["endurain://cb", "gadgetbridge://auth"]

    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_excludes_admin_only_fields(self, mock_get, mock_db):
        """Test sign-up policy and the tile API key never reach the public shape."""
        mock_get.return_value = self._stored_settings()

        dumped = server_settings_service.get_server_settings_for_public(mock_db).model_dump()

        assert "signup_require_admin_approval" not in dumped
        assert "tileserver_api_key" not in dumped
        assert "allowed_redirect_schemes" not in dumped


class TestEditMailSettingsLocking:
    """The validation that can resolve DNS runs before the settings row is locked."""

    def test_validation_runs_before_the_row_is_locked(self, mail_env):
        calls = []
        mail_env.read.side_effect = lambda db, **kwargs: (calls.append(("read", kwargs)), mail_env.stored)[1]
        with patch.object(
            core_mail,
            "mail_problems",
            side_effect=lambda config: calls.append(("dns", {})) or [],
        ):
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
            )

        # The last check is the one that builds the email status of the saved settings.
        assert [name for name, _ in calls] == ["read", "dns", "read", "dns"]
        assert calls[2][1] == {"for_update": True}

    def test_a_password_replaced_meanwhile_is_refused(self, mail_env):
        later = mail_env.stored.model_copy(update={"password": "enc-new"})
        mail_env.read.side_effect = [mail_env.stored, later]

        with pytest.raises(core_exceptions.PreconditionFailedError):
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
            )

        mail_env.write.assert_not_called()


class TestSettingsAudit:
    def test_a_changed_setting_stages_its_field_name_only(self, edit_env):
        db = MagicMock()
        with jasil_testing.capture_audit() as audit:
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, currency="dollar", tileserver_api_key="plain-new"),
                None,
                VERIFIER,
                db,
                if_match="*",
            )

        entry = audit.assert_audited(server_settings_audit_actions.SETTINGS_UPDATE.id)
        assert entry.details == {"changed_fields": ["currency", "tileserver_api_key"]}

    def test_turning_the_breach_check_on_is_audited_by_field_name_only(self, edit_env):
        with jasil_testing.capture_audit() as audit:
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, password_breach_check_enabled=True),
                None,
                VERIFIER,
                MagicMock(),
                if_match="*",
            )

        entry = audit.assert_audited(server_settings_audit_actions.SETTINGS_UPDATE.id)
        assert entry.details == {"changed_fields": ["password_breach_check_enabled"]}

    def test_changing_the_mfa_requirement_is_audited_by_field_name_only(self, edit_env):
        with jasil_testing.capture_audit() as audit:
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, require_mfa="everyone"),
                auth_schema.StepUpVerification(current_password="admin-password"),
                MagicMock(),
                MagicMock(),
                if_match="*",
            )

        entry = audit.assert_audited(server_settings_audit_actions.SETTINGS_UPDATE.id)
        assert entry.details == {"changed_fields": ["require_mfa"]}

    def test_the_row_is_staged_before_the_commit_of_a_tile_change(self, edit_env):
        db = MagicMock()
        with jasil_testing.capture_audit() as audit:
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, map_background_color="#000000"), None, VERIFIER, db, if_match="*"
            )

        audit.assert_audited(server_settings_audit_actions.SETTINGS_UPDATE.id)
        edit_env.publish.assert_called_once()

    def test_resending_the_unchanged_record_is_not_audited(self, edit_env):
        with jasil_testing.capture_audit() as audit:
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored), None, VERIFIER, MagicMock(), if_match="*"
            )

        audit.assert_not_audited(server_settings_audit_actions.SETTINGS_UPDATE.id)


class TestMailSettingsAudit:
    def test_a_changed_password_appears_as_its_field_name_only(self, mail_env):
        with jasil_testing.capture_audit() as audit:
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465, password="plain-new"),
                _STEP_UP,
                _VERIFY,
                MagicMock(),
                if_match="*",
            )

        entry = audit.assert_audited(server_settings_audit_actions.MAIL_UPDATE.id)
        assert entry.details == {"changed_fields": ["password", "port"]}

    def test_resending_the_unchanged_record_is_not_audited(self, mail_env):
        with jasil_testing.capture_audit() as audit:
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored), _STEP_UP, _VERIFY, MagicMock(), if_match="*"
            )

        audit.assert_not_audited(server_settings_audit_actions.MAIL_UPDATE.id)


class TestLoginPhotoAudit:
    def test_an_upload_is_audited_without_a_file_name(self):
        with (
            patch.object(core_file_uploads, "read_validated_upload_sync", return_value=_PNG),
            patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)),
            jasil_testing.capture_audit() as audit,
        ):
            server_settings_login_photo_service.upload_login_photo(MagicMock(), MagicMock(), MagicMock())

        entry = audit.assert_audited(server_settings_audit_actions.LOGIN_PHOTO_UPDATE.id)
        assert entry.details is None

    def test_a_refused_upload_is_not_audited(self):
        with (
            patch.object(core_file_uploads, "read_validated_upload_sync", return_value=b"not an image"),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            server_settings_login_photo_service.upload_login_photo(MagicMock(), MagicMock(), MagicMock())

        audit.assert_not_audited(server_settings_audit_actions.LOGIN_PHOTO_UPDATE.id)

    def test_a_removal_is_audited_even_when_the_blob_cannot_be_deleted(self):
        storage = MagicMock()
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("storage down")
        with (
            patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)),
            jasil_testing.capture_audit() as audit,
        ):
            server_settings_login_photo_service.delete_login_photo(storage, MagicMock())

        entry = audit.assert_audited(server_settings_audit_actions.LOGIN_PHOTO_DELETE.id)
        assert entry.details is None


class TestLoginPhotoImageFormats:
    def _upload(self, name: str, data: bytes) -> UploadFile:
        return UploadFile(io.BytesIO(data), filename=name)

    def test_a_webp_is_stored_without_its_metadata(self):
        storage = MagicMock()

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo", return_value=(4, False)):
            server_settings_login_photo_service.upload_login_photo(
                self._upload("login.webp", images.webp_with_exif()), storage, MagicMock()
            )

        _area, _key, data, content_type = storage.save.call_args.args
        assert content_type == "image/webp"
        assert not images.has_metadata(data)

    @pytest.mark.parametrize(
        ("name", "data"), [("a.gif", images.gif()), ("a.heic", images.heic_like())], ids=["gif", "heic"]
    )
    def test_gif_and_heic_are_refused(self, name: str, data: bytes):
        storage = MagicMock()

        with pytest.raises(core_exceptions.DomainError) as exc:
            server_settings_login_photo_service.upload_login_photo(self._upload(name, data), storage, MagicMock())

        assert exc.value.status_code == 415
        storage.save.assert_not_called()


class TestMailSettingsStepUp:
    def test_the_step_up_is_verified_for_the_mail_action_before_anything_is_read(self, mail_env):
        verifier = MagicMock()
        order = MagicMock()
        order.attach_mock(verifier, "step_up")
        order.attach_mock(mail_env.read, "read")

        server_settings_mail_service.edit_mail_settings(
            _mail_edit(mail_env.stored, port=465), _STEP_UP, verifier, MagicMock(), if_match="*"
        )

        assert order.mock_calls[0][0] == "step_up"
        verifier.assert_called_once_with(_STEP_UP, idp_constants.StepUpAction.ADMIN_MAIL_SETTINGS_EDIT)

    def test_a_refused_step_up_reads_validates_and_writes_nothing(self, mail_env):
        db = MagicMock()

        with pytest.raises(core_exceptions.StepUpFailedError):
            server_settings_mail_service.edit_mail_settings(
                _mail_edit(mail_env.stored, port=465),
                _STEP_UP,
                MagicMock(side_effect=core_exceptions.StepUpFailedError()),
                db,
                if_match="*",
            )

        mail_env.read.assert_not_called()
        mail_env.problems.assert_not_called()
        mail_env.write.assert_not_called()
        db.commit.assert_not_called()


class TestGetAccessPolicy:
    """The per-request read that resolves a principal: the session policy and the MFA requirement, in one read."""

    @pytest.mark.parametrize("value", ["off", "administrators", "everyone"])
    def test_it_carries_the_session_policy_and_the_mfa_requirement(self, value):
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=_stored(require_mfa=value)
        ) as read:
            policy = server_settings_service.get_access_policy(MagicMock())

        read.assert_called_once()
        assert policy.require_mfa == server_settings_contracts.RequireMfa(value)
        assert policy.session.access_token_ttl == timedelta(minutes=15)

    def test_a_missing_settings_row_is_a_service_error(self):
        with (
            patch.object(server_settings_service.server_settings_crud, "get_server_settings", return_value=None),
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            server_settings_service.get_access_policy(MagicMock())


class TestRequireMfaCoverage:
    """Who the setting covers."""

    @pytest.mark.parametrize(
        ("value", "admin", "regular"),
        [("off", False, False), ("administrators", True, False), ("everyone", True, True)],
    )
    def test_each_value_covers_its_accounts(self, value, admin, regular):
        policy_value = server_settings_contracts.RequireMfa(value)

        assert policy_value.covers(is_admin=True) is admin
        assert policy_value.covers(is_admin=False) is regular
