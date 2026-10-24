"""Tests for the transactional email helpers."""

from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import jasil.settings as jasil_settings
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

    def test_the_mapped_settings_are_what_is_validated(self):
        with patch.object(core_mail.jasil_settings, "mail_problems", return_value=[]) as validate:
            core_mail.mail_problems(_config())

        assert validate.call_args.args[0] == core_mail.to_mail_settings(_config())

    def test_sound_settings_have_no_problems(self):
        assert core_mail.mail_problems(_config()) == []

    def test_messages_never_contain_values(self):
        problems = core_mail.mail_problems(
            _config(username="me@example.com", password=None, from_address="bad address")
        )

        assert problems
        assert all("secret" not in p and "bad address" not in p and "me@example.com" not in p for p in problems)
