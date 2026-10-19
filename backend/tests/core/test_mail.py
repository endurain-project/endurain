"""Tests for the transactional email helpers."""

from unittest.mock import MagicMock

import jasil.providers as platform_providers
import pytest

import core.mail as core_mail


def _send(mail: MagicMock) -> bool:
    return core_mail.send_email(mail, "user@example.com", "Subject", "<p>html</p>", "text")


class TestSendEmail:
    def test_builds_message_with_both_bodies(self):
        mail = MagicMock()

        assert _send(mail) is True

        message = mail.send.call_args.args[0]
        assert message.to == ["user@example.com"]
        assert message.subject == "Subject"
        assert message.html == "<p>html</p>"
        assert message.text == "text"

    def test_not_configured_is_dropped(self):
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailNotConfiguredError("not configured")

        assert _send(mail) is False

    def test_permanent_refusal_is_dropped(self):
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("refused", status=550)

        assert _send(mail) is False

    def test_invalid_message_is_dropped(self):
        mail = MagicMock()
        mail.send.side_effect = ValueError("bad address")

        assert _send(mail) is False

    @pytest.mark.parametrize("status", [None, 421, 451])
    def test_transient_failure_propagates(self, status):
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("transient", status=status)

        with pytest.raises(platform_providers.MailError):
            _send(mail)
