"""Tests for the server-settings test email builder."""

import modules.server_settings.email_messages as email_messages


class TestGetTestEmail:
    def test_returns_subject_html_and_text(self):
        subject, html_body, text_body = email_messages.get_test_email(
            "Alice", "mail.example.com:587", "https://endurain.example.com", "en"
        )

        assert "Endurain" in subject
        assert "mail.example.com:587" in html_body
        assert "mail.example.com:587" in text_body
        assert "Alice" in text_body

    def test_user_controlled_values_are_html_escaped(self):
        _, html_body, _ = email_messages.get_test_email(
            "<script>alert(1)</script>", "<b>host</b>:25", "https://endurain.example.com", "en"
        )

        assert "<script>alert(1)</script>" not in html_body
        assert "<b>host</b>" not in html_body

    def test_unsupported_locale_falls_back_to_english(self):
        subject, _, _ = email_messages.get_test_email("A", "h:25", "https://e.example.com", "xx")

        assert subject == "Endurain - Test email"
