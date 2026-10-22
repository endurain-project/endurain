"""Tests for the server-settings write path.

The service is where the tile-URL network policy is enforced: the schema is also
what deserializes settings on every *read*, so a validator there would put a DNS
lookup on the read path of the whole app.
"""

from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from fastapi import HTTPException

import core.exceptions as core_exceptions
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service


def _stored(**overrides) -> server_settings_schema.ServerSettingsRead:
    """Settings as the crud layer returns them (the tile API key still encrypted)."""
    values = dict(
        id=1,
        units="metric",
        public_shareable_links=False,
        public_shareable_links_user_info=False,
        login_photo_set=False,
        currency="euro",
        num_records_per_page=25,
        signup_enabled=False,
        signup_require_admin_approval=True,
        signup_require_email_verification=True,
        sso_enabled=False,
        local_login_enabled=True,
        sso_auto_redirect=False,
        tileserver_url="https://tiles.example.com/{z}/{x}/{y}.png",
        tileserver_attribution="Test",
        map_background_color="#dddddd",
        password_type="strict",
        tileserver_regenerate_thumbnails_on_change=False,
        password_length_regular_users=8,
        password_length_admin_users=12,
        tileserver_api_key="enc-old",
    )
    values.update(overrides)
    return server_settings_schema.ServerSettingsRead(**values)


def _full_edit(stored: server_settings_schema.ServerSettingsRead, **overrides):
    """The whole record, the way the frontend sends it on every save (key in plain text)."""
    body = stored.model_dump(exclude={"id", "login_photo_set"})
    body["tileserver_api_key"] = "plain-old"
    body.update(overrides)
    return server_settings_schema.ServerSettingsEdit(**body)


_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


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
        patch.object(server_settings_service.core_network, "url_rejection_reason_bounded", return_value=None) as dns,
        patch.object(
            server_settings_service.core_cryptography,
            "decrypt_token_fernet",
            side_effect=lambda token: {"enc-old": "plain-old", "enc-new": "plain-new"}[token],
        ),
        patch.object(server_settings_service.core_cryptography, "encrypt_token_fernet", return_value="enc-new"),
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
                _full_edit(edit_env.stored, tileserver_url="https://internal.example.com/{z}/{x}/{y}.png"), db
            )

        edit_env.write.assert_not_called()
        db.commit.assert_not_called()

    def test_the_placeholders_are_filled_before_the_check(self, edit_env):
        """``{z}/{x}/{y}`` is not a parseable URL; the host is what matters."""
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_url="https://other.example.com/{z}/{x}/{y}.png"), MagicMock()
        )

        assert edit_env.dns.call_args.args[0] == "https://other.example.com/0/0/0.png"

    @pytest.mark.parametrize(
        "template", [t["url_template"] for t in server_settings_constants.TILE_MAPS_TEMPLATES.values()]
    )
    def test_every_builtin_template_can_be_saved(self, edit_env, template):
        """``{r}`` (Stadia retina) is dropped by the renderer, so it must not be a 400."""
        server_settings_service.edit_server_settings(_full_edit(edit_env.stored, tileserver_url=template), MagicMock())

        assert "{" not in edit_env.dns.call_args.args[0]

    def test_an_unfillable_placeholder_is_a_400_not_a_background_500(self, edit_env):
        """The renderer resolves the same template before every tile fetch."""
        with pytest.raises(core_exceptions.InvalidInputError):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_url="https://tiles.example.com/{}/{z}/{x}/{y}.png"), MagicMock()
            )

        edit_env.write.assert_not_called()


class TestOnlyRealChangesCount:
    def test_resending_the_unchanged_record_does_nothing(self, edit_env):
        """The frontend sends every field on every save; that must not look like a tile change."""
        db = MagicMock()

        result = server_settings_service.edit_server_settings(_full_edit(edit_env.stored), db)

        edit_env.dns.assert_not_called()
        edit_env.write.assert_not_called()
        edit_env.publish.assert_not_called()
        db.commit.assert_not_called()
        assert result.tileserver_api_key_set is True
        assert not hasattr(result, "tileserver_api_key")

    def test_a_non_tile_change_commits_without_publishing(self, edit_env):
        db = MagicMock()

        server_settings_service.edit_server_settings(_full_edit(edit_env.stored, currency="dollar"), db)

        edit_env.dns.assert_not_called()
        edit_env.publish.assert_not_called()
        db.commit.assert_called_once()

    def test_a_tile_change_publishes_only_the_changed_map_fields(self, edit_env):
        server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, map_background_color="#000000"), MagicMock()
        )

        assert edit_env.publish.call_args.args[0] == {"map_background_color"}
        edit_env.dns.assert_not_called()

    def test_an_unchanged_api_key_keeps_its_stored_token(self, edit_env):
        server_settings_service.edit_server_settings(_full_edit(edit_env.stored, currency="dollar"), MagicMock())

        written = edit_env.write.call_args.args[0]
        assert written.tileserver_api_key == "enc-old"

    def test_a_changed_api_key_is_encrypted_and_never_returned(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_api_key="plain-new"), MagicMock()
        )

        assert edit_env.write.call_args.args[0].tileserver_api_key == "enc-new"
        assert result.tileserver_api_key_set is True
        assert "plain-new" not in result.model_dump_json()
        assert edit_env.publish.call_args.args[0] == {"tileserver_api_key"}

    def test_clearing_the_api_key_stores_none(self, edit_env):
        result = server_settings_service.edit_server_settings(
            _full_edit(edit_env.stored, tileserver_api_key=None), MagicMock()
        )

        assert edit_env.write.call_args.args[0].tileserver_api_key is None
        assert result.tileserver_api_key_set is False

    def test_an_undecryptable_stored_key_can_be_replaced(self, edit_env):
        """After the encryption key changes, re-entering the key must still work."""
        with patch.object(
            server_settings_service.core_cryptography,
            "decrypt_token_fernet",
            side_effect=HTTPException(status_code=500, detail="Internal Server Error"),
        ):
            server_settings_service.edit_server_settings(
                _full_edit(edit_env.stored, tileserver_api_key="plain-new"), MagicMock()
            )

        assert edit_env.write.call_args.args[0].tileserver_api_key == "enc-new"

    def test_the_row_is_locked_for_the_edit(self, edit_env):
        db = MagicMock()
        with patch.object(
            server_settings_service.server_settings_crud, "get_server_settings", return_value=edit_env.stored
        ) as read:
            server_settings_service.edit_server_settings(_full_edit(edit_env.stored, currency="dollar"), db)

        read.assert_called_once_with(db, for_update=True)


class TestLoginPhoto:
    def test_upload_writes_the_blob_before_committing_the_flag(self):
        calls = []
        storage = MagicMock()
        storage.save.side_effect = lambda *a: calls.append("save")
        db = MagicMock()
        db.commit.side_effect = lambda: calls.append("commit")
        file = MagicMock(content_type="text/plain")

        with (
            patch.object(server_settings_service.core_file_uploads, "read_validated_upload_sync", return_value=_PNG),
            patch.object(server_settings_service.server_settings_crud, "set_login_photo"),
        ):
            server_settings_service.upload_login_photo(file, storage, db)

        assert calls == ["save", "commit"]
        # The type is detected from the bytes, not taken from the client's claim.
        storage.save.assert_called_once_with("server_images", "login.png", _PNG, "image/png")

    def test_upload_rejects_a_photo_over_the_login_cap(self):
        big = _PNG + b"0" * server_settings_constants.LOGIN_PHOTO_MAX_BYTES
        storage = MagicMock()

        with (
            patch.object(server_settings_service.core_file_uploads, "read_validated_upload_sync", return_value=big),
            pytest.raises(core_exceptions.PayloadTooLargeError),
        ):
            server_settings_service.upload_login_photo(MagicMock(), storage, MagicMock())

        storage.save.assert_not_called()

    def test_upload_rejects_an_unrecognised_format(self):
        storage = MagicMock()

        with (
            patch.object(
                server_settings_service.core_file_uploads, "read_validated_upload_sync", return_value=b"not an image"
            ),
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            server_settings_service.upload_login_photo(MagicMock(), storage, MagicMock())

        storage.save.assert_not_called()

    def test_delete_clears_the_flag_before_removing_the_blob(self):
        calls = []
        storage = MagicMock()
        storage.delete.side_effect = lambda *a: calls.append("delete")
        db = MagicMock()
        db.commit.side_effect = lambda: calls.append("commit")

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo"):
            server_settings_service.delete_login_photo(storage, db)

        assert calls == ["commit", "delete"]
        storage.delete.assert_called_once_with("server_images", "login.png")

    def test_delete_survives_a_storage_failure(self):
        storage = MagicMock()
        storage.delete.side_effect = RuntimeError("storage down")
        db = MagicMock()

        with patch.object(server_settings_service.server_settings_crud, "set_login_photo"):
            server_settings_service.delete_login_photo(storage, db)

        db.commit.assert_called_once()

    def test_read_returns_none_when_not_set_without_calling_storage(self):
        storage = MagicMock()

        with patch.object(
            server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=False)
        ):
            assert server_settings_service.read_login_photo(storage, MagicMock()) is None

        storage.get.assert_not_called()

    def test_read_returns_none_when_missing(self):
        storage = MagicMock()
        storage.get.return_value = None

        with patch.object(server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=True)):
            assert server_settings_service.read_login_photo(storage, MagicMock()) is None

    @pytest.mark.parametrize(
        "data,media_type",
        [(_PNG, "image/png"), (b"\xff\xd8\xff\xe0", "image/jpeg"), (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp")],
    )
    def test_read_returns_the_detected_type(self, data, media_type):
        storage = MagicMock()
        storage.get.return_value = data

        with patch.object(server_settings_service, "get_server_settings", return_value=MagicMock(login_photo_set=True)):
            assert server_settings_service.read_login_photo(storage, MagicMock()) == (data, media_type)


class TestEmailStatus:
    """Test suite for get_email_status."""

    @patch("modules.server_settings.service.core_mail.is_mail_configured", return_value=True)
    def test_configured(self, _configured):
        result = server_settings_service.get_email_status()

        assert result.configured is True

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.core_mail.is_mail_configured", return_value=False)
    def test_unset_host_reports_missing_host(self, _configured, mock_settings):
        mock_settings.SMTP_HOST = None
        mock_settings.mail_problems = []

        result = server_settings_service.get_email_status()

        assert result.configured is False
        assert result.problems == ["SMTP_HOST is not set"]

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.core_mail.is_mail_configured", return_value=False)
    def test_invalid_settings_report_problems(self, _configured, mock_settings):
        mock_settings.SMTP_HOST = "mail.example.com"
        mock_settings.mail_problems = ["SMTP_USERNAME and SMTP_PASSWORD must be set together"]

        result = server_settings_service.get_email_status()

        assert result.problems == ["SMTP_USERNAME and SMTP_PASSWORD must be set together"]


class TestSendTestEmail:
    """Test suite for send_test_email."""

    @staticmethod
    def _admin():
        return MagicMock(email="admin@example.com", preferred_language="en", **{"name": "Admin"})

    @patch("modules.server_settings.service.get_email_status")
    def test_not_configured_raises_503_with_reasons(self, mock_status):
        mock_status.return_value = server_settings_schema.EmailStatus(
            configured=False, problems=["SMTP_HOST is not set"]
        )
        mail = MagicMock()

        with pytest.raises(core_exceptions.ServiceUnavailableError) as exc_info:
            server_settings_service.send_test_email(self._admin(), mail)

        assert "SMTP_HOST is not set" in exc_info.value.detail
        mail.send.assert_not_called()

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.get_email_status")
    def test_sends_to_the_admin_only(self, mock_status, mock_settings):
        mock_status.return_value = server_settings_schema.EmailStatus(configured=True, problems=[])
        mock_settings.SMTP_HOST = "mail.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.ENDURAIN_HOST = "https://endurain.example.com"
        mail = MagicMock()

        server_settings_service.send_test_email(self._admin(), mail)

        message = mail.send.call_args.args[0]
        assert message.to == ["admin@example.com"]
        assert "mail.example.com:587" in message.text
        assert message.html and message.text

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.get_email_status")
    def test_mail_error_becomes_502_with_status_code(self, mock_status, mock_settings):
        mock_status.return_value = server_settings_schema.EmailStatus(configured=True, problems=[])
        mock_settings.SMTP_HOST = "mail.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.ENDURAIN_HOST = "https://endurain.example.com"
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("SMTP authentication failed (status 535)", status=535)

        with pytest.raises(core_exceptions.UpstreamError) as exc_info:
            server_settings_service.send_test_email(self._admin(), mail)

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
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            tileserver_regenerate_thumbnails_on_change=False,
            password_length_regular_users=8,
            password_length_admin_users=12,
            tileserver_api_key="encrypted",
        )

    @patch("modules.server_settings.service.core_config.settings")
    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_reflects_configured_schemes_sorted(self, mock_get, mock_config, mock_db):
        """Test the redirect schemes mirror ALLOWED_REDIRECT_SCHEMES, sorted."""
        mock_get.return_value = self._stored_settings()
        mock_config.ALLOWED_REDIRECT_SCHEMES = {"gadgetbridge", "endurain"}

        result = server_settings_service.get_server_settings_for_public(mock_db)

        assert result.allowed_redirect_schemes == ["endurain", "gadgetbridge"]

    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_excludes_admin_only_fields(self, mock_get, mock_db):
        """Test sign-up policy and the tile API key never reach the public shape."""
        mock_get.return_value = self._stored_settings()

        dumped = server_settings_service.get_server_settings_for_public(mock_db).model_dump()

        assert "signup_require_admin_approval" not in dumped
        assert "tileserver_api_key" not in dumped
