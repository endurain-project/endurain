"""Tests for the transactional email helpers."""

from unittest.mock import patch

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import jasil.settings as jasil_settings
import pytest
from jasil.backends.mail_memory import NullMail

import core.mail as core_mail


def _send(mail: platform_providers.MailProvider, to: str = "user@example.com") -> bool:
    return core_mail.send_email(mail, to, "Subject", "<p>html</p>", "text")


class _RefusingMail:
    """A mail server that answers every message with an error, as SMTP does."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def send(self, message: platform_providers.MailMessage) -> str:
        raise self.error


class TestSendEmail:
    def test_builds_message_with_both_bodies(self):
        mail = platform_runtime.get_active_platform().mail

        assert _send(mail) is True

        (message,) = mail.outbox
        assert message.to == ["user@example.com"]
        assert message.subject == "Subject"
        assert message.html == "<p>html</p>"
        assert message.text == "text"

    def test_not_configured_is_dropped(self):
        assert _send(NullMail()) is False

    def test_permanent_refusal_is_dropped(self):
        assert _send(_RefusingMail(platform_providers.MailError("refused", status=550))) is False

    def test_invalid_message_is_dropped(self):
        mail = platform_runtime.get_active_platform().mail

        assert _send(mail, to="not an address") is False
        assert mail.outbox == []

    @pytest.mark.parametrize("status", [None, 421, 451])
    def test_transient_failure_propagates(self, status):
        with pytest.raises(platform_providers.MailError):
            _send(_RefusingMail(platform_providers.MailError("transient", status=status)))


def _config(**overrides) -> core_mail.MailConfig:
    values = dict(
        host="mail.example.com",
        port=587,
        security=core_mail.MailSecurity.STARTTLS,
        from_address="me@example.com",
        username="me@example.com",
        password="secret",
    )
    values.update(overrides)
    return core_mail.MailConfig(**values)


class TestToMailSettings:
    def test_none_is_unset(self):
        assert core_mail.to_mail_settings(None) == jasil_settings.MailSettings()

    def test_starttls_maps_to_smtp_with_credentials_and_display_name(self):
        result = core_mail.to_mail_settings(_config())

        assert result.uri == "smtp://mail.example.com:587"
        assert result.secure is True
        assert result.username == "me@example.com"
        assert result.password == "secret"
        assert result.from_address == "Endurain <me@example.com>"

    def test_ssl_maps_to_smtps(self):
        result = core_mail.to_mail_settings(_config(security=core_mail.MailSecurity.SSL, port=465))

        assert result.uri == "smtps://mail.example.com:465"
        assert result.secure is True

    def test_none_maps_to_cleartext(self):
        result = core_mail.to_mail_settings(_config(security=core_mail.MailSecurity.NONE, username=None, password=None))

        assert result.uri == "smtp://mail.example.com:587"
        assert result.secure is False

    def test_an_ipv6_literal_is_bracketed(self):
        assert core_mail.to_mail_settings(_config(host="::1")).uri == "smtp://[::1]:587"

    def test_an_explicit_display_name_is_kept(self):
        result = core_mail.to_mail_settings(_config(from_address="Team <team@example.com>"))

        assert result.from_address == "Team <team@example.com>"

    def test_a_missing_sender_stays_empty(self):
        assert core_mail.to_mail_settings(_config(from_address="")).from_address == ""


class TestMailProblems:
    @staticmethod
    def _problem(code):
        return jasil_settings.MailProblem(code, "mail.uri", "names jasil.setting paths")

    @pytest.mark.parametrize("code", list(core_mail._PROBLEM_MESSAGES))
    def test_each_known_code_has_its_own_message(self, code):
        with patch.object(core_mail.jasil_settings, "mail_problems", return_value=[self._problem(code)]):
            assert core_mail.mail_problems(_config()) == [core_mail._PROBLEM_MESSAGES[code]]

    def test_an_unknown_code_gets_the_fallback(self):
        problem = self._problem(jasil_settings.MailProblemCode.INVALID_URI)
        with patch.object(core_mail.jasil_settings, "mail_problems", return_value=[problem]):
            assert core_mail.mail_problems(_config()) == ["The mail settings are not valid"]

    def test_repeated_messages_are_listed_once(self):
        problems = [self._problem(jasil_settings.MailProblemCode.INVALID_URI)] * 2
        with patch.object(core_mail.jasil_settings, "mail_problems", return_value=problems):
            assert len(core_mail.mail_problems(_config())) == 1

    def test_sound_settings_have_no_problems(self):
        assert core_mail.mail_problems(_config()) == []

    def test_messages_never_contain_values(self):
        problems = core_mail.mail_problems(
            _config(username="me@example.com", password=None, from_address="bad address")
        )

        assert problems
        assert all("secret" not in p and "bad address" not in p and "me@example.com" not in p for p in problems)


class TestRefusalLevels:
    """A refused message is a recipient or data problem the operator sees, not a fault of this server."""

    def test_a_message_the_server_refused_is_a_warning(self, caplog):
        mail = _RefusingMail(platform_providers.MailError("refused", status=550))

        with caplog.at_level("DEBUG", logger=core_mail.logger.name):
            _send(mail)

        assert [record.levelname for record in caplog.records] == ["WARNING"]

    def test_an_invalid_message_is_a_warning(self, caplog):
        with caplog.at_level("DEBUG", logger=core_mail.logger.name):
            _send(platform_runtime.get_active_platform().mail, to="not an address")

        assert [record.levelname for record in caplog.records] == ["WARNING"]
