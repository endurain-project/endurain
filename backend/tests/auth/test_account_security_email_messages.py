"""Tests for the account-security change email builder."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import modules.auth.account_security.email_messages as email_messages
import modules.auth.account_security.events as account_security_events

HOST = "https://endurain.example.com"
CHANGES = [change.value for change in account_security_events.AccountSecurityChange] + [
    email_messages.IDENTITY_PROVIDER_LINKED
]


class TestGetAccountSecurityChangedEmail:
    @pytest.mark.parametrize("change", CHANGES)
    def test_every_change_has_its_own_subject_and_sentence(self, change):
        subject, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", change, "Authentik", HOST, "en"
        )

        assert subject.startswith("Endurain - ")
        assert "account_security_changed." not in subject + html_body + text_body
        assert "Hi Alice," in html_body
        assert "Hi Alice," in text_body

    def test_subjects_differ_per_change(self):
        subjects = {
            email_messages.get_account_security_changed_email("Alice", change, None, HOST, "en")[0]
            for change in CHANGES
        }

        assert len(subjects) == len(CHANGES)

    def test_a_password_change_warns_to_reset_the_password(self):
        _, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "password_changed", None, HOST, "en"
        )

        assert "reset your password" in html_body
        assert "reset your password" in text_body

    def test_a_change_made_by_an_administrator_says_to_contact_one(self):
        _, html_body, _ = email_messages.get_account_security_changed_email(
            "Alice", "password_set_by_admin", None, HOST, "en"
        )

        assert "administrator" in html_body
        assert "reset your password" not in html_body

    def test_a_locked_account_says_what_is_refused_for_how_long_and_how_to_lift_it(self):
        _, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", "account_locked", None, HOST, "en"
        )

        for body in (html_body, text_body):
            assert "100 failed sign-in attempts in a row" in body
            assert "30 days" in body
            assert "Change or reset your password" in body

    @pytest.mark.parametrize("change", ["identity_provider_unlinked", "identity_provider_linked"])
    def test_names_the_provider_when_it_exists(self, change):
        _, html_body, text_body = email_messages.get_account_security_changed_email(
            "Alice", change, "Authentik", HOST, "en"
        )

        assert "Authentik" in html_body
        assert "Authentik" in text_body

    def test_omits_the_provider_name_when_it_is_gone(self):
        _, html_body, _ = email_messages.get_account_security_changed_email(
            "Alice", "identity_provider_unlinked", None, HOST, "en"
        )

        assert "None" not in html_body
        assert "{provider}" not in html_body

    def test_escapes_the_name_and_the_provider(self):
        _, html_body, _ = email_messages.get_account_security_changed_email(
            "<b>Al</b>", "identity_provider_linked", "<script>x</script>", HOST, "en"
        )

        assert "<b>Al</b>" not in html_body
        assert "<script>x</script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_an_unknown_change_is_refused(self):
        with pytest.raises(ValueError):
            email_messages.get_account_security_changed_email("Alice", "nope", None, HOST, "en")


class TestGetNewDeviceSignInEmail:
    def _build(self, **overrides):
        values = {
            "user_name": "Alice",
            "browser": "Firefox",
            "operating_system": "Linux",
            "ip_address": "203.0.113.7",
            "method": "password",
            "signed_in_at": datetime(2026, 11, 1, 13, 5, tzinfo=ZoneInfo("Europe/Lisbon")),
            "frontend_host": HOST,
            "locale": "en",
        }
        values.update(overrides)
        return email_messages.get_new_device_sign_in_email(**values)

    def test_says_when_from_what_browser_and_address_and_how(self):
        subject, html_body, text_body = self._build()

        assert subject.startswith("Endurain - ")
        for body in (html_body, text_body):
            assert "Hi Alice," in body
            assert "2026-11-01 13:05 WET" in body
            assert "Firefox on Linux" in body
            assert "203.0.113.7" in body
            assert "Password" in body
            assert "new_device_sign_in." not in body

    def test_names_a_sign_in_provider(self):
        _, html_body, text_body = self._build(method="identity_provider")

        assert "sign-in provider" in html_body
        assert "sign-in provider" in text_body

    def test_tells_the_reader_to_change_the_password_and_sign_out_other_sessions(self):
        _, html_body, text_body = self._build()

        for body in (html_body, text_body):
            assert "change your password" in body
            assert "sign out of your other sessions" in body

    def test_escapes_everything_it_interpolates(self):
        _, html_body, _ = self._build(
            user_name="<b>Al</b>",
            browser="<script>b</script>",
            operating_system="<i>os</i>",
            ip_address="<img src=x>",
        )

        for raw in ("<b>Al</b>", "<script>b</script>", "<i>os</i>", "<img src=x>"):
            assert raw not in html_body
        assert "&lt;script&gt;b&lt;/script&gt; on &lt;i&gt;os&lt;/i&gt;" in html_body
        assert "&lt;img src=x&gt;" in html_body

    def test_an_unknown_method_is_refused(self):
        with pytest.raises(ValueError):
            self._build(method="carrier_pigeon")
