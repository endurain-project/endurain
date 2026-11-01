"""Tests for the account-security change email builder."""

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
