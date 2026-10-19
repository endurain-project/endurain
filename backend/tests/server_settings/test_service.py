"""Tests for the server-settings write path.

The service is where the tile-URL network policy is enforced: the schema is also
what deserializes settings on every *read*, so a validator there would put a DNS
lookup on the read path of the whole app.
"""

from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest

import core.exceptions as core_exceptions
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service


def _attributes(**overrides):
    attrs = MagicMock()
    attrs.model_dump.return_value = overrides.pop("changed", {"tileserver_url": True})
    attrs.tileserver_url = overrides.pop("tileserver_url", "https://tiles.example.com/{z}/{x}/{y}.png")
    return attrs


class TestTileServerUrlIsCheckedOnWrite:
    def test_a_url_targeting_a_non_public_address_is_refused(self):
        """The renderer refuses it too, but only later, in a background job.

        By then the admin has seen no error and the bad value is already stored.
        """
        db = MagicMock()
        with (
            patch.object(
                server_settings_service.core_network,
                "url_rejection_reason",
                return_value="resolves to a non-public address",
            ),
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings") as write,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            server_settings_service.edit_server_settings(_attributes(), db)

        write.assert_not_called()
        db.commit.assert_not_called()

    def test_the_placeholders_are_filled_before_the_check(self):
        """``{z}/{x}/{y}`` is not a parseable URL; the host is what matters."""
        db = MagicMock()
        with (
            patch.object(server_settings_service.core_network, "url_rejection_reason", return_value=None) as check,
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings"),
            patch.object(server_settings_service.server_settings_publishers, "publish_tile_settings_changed"),
        ):
            server_settings_service.edit_server_settings(_attributes(), db)

        assert check.call_args.args[0] == "https://tiles.example.com/0/0/0.png"

    def test_an_untouched_tile_url_is_not_resolved(self):
        """A settings write that does not change it must not pay for a lookup."""
        db = MagicMock()
        with (
            patch.object(server_settings_service.core_network, "url_rejection_reason") as check,
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings"),
        ):
            server_settings_service.edit_server_settings(_attributes(changed={"currency": "euro"}), db)

        check.assert_not_called()
        db.commit.assert_called_once()

    def test_an_unfillable_placeholder_is_a_400_not_a_background_500(self):
        """The renderer resolves the same template before every tile fetch."""
        db = MagicMock()
        with (
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings") as write,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            server_settings_service.edit_server_settings(
                _attributes(tileserver_url="https://tiles.example.com/{s}/{z}/{x}/{y}.png"), db
            )

        write.assert_not_called()


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
