"""Tests for sign-up email message builders."""

from unittest.mock import MagicMock

import modules.auth.sign_up_tokens.email_messages as email_messages


def _make_service(frontend_host: str = "https://endurain.example.com"):
    """Build a minimal AppriseService mock."""
    svc = MagicMock()
    svc.frontend_host = frontend_host
    return svc


class TestGetSignupConfirmationEmail:
    """Tests for get_signup_confirmation_email."""

    def test_returns_three_tuple(self):
        """Builder returns (subject, html, text) tuple."""
        result = email_messages.get_signup_confirmation_email(
            "Alice",
            "https://example.com/verify?token=abc",
            _make_service(),
            locale="en",
        )
        assert len(result) == 3

    def test_html_lang_us(self):
        """HTML uses lang='en-US' for the 'en' locale."""
        _, html_body, _ = email_messages.get_signup_confirmation_email(
            "Alice",
            "https://example.com/verify?token=abc",
            _make_service(),
            locale="en",
        )
        assert 'lang="en-US"' in html_body

    def test_html_lang_pt(self):
        """HTML uses lang='pt-PT' for the 'pt-PT' locale."""
        _, html_body, _ = email_messages.get_signup_confirmation_email(
            "Alice",
            "https://example.com/verify",
            _make_service(),
            locale="pt-PT",
        )
        assert 'lang="pt-PT"' in html_body

    def test_html_contains_signup_link(self):
        """HTML body contains the signup link."""
        link = "https://example.com/verify?token=xyz"
        _, html_body, _ = email_messages.get_signup_confirmation_email("Alice", link, _make_service(), locale="en")
        assert link in html_body

    def test_text_contains_signup_link(self):
        """Plain-text body contains the signup link."""
        link = "https://example.com/verify?token=xyz"
        _, _, text_body = email_messages.get_signup_confirmation_email("Alice", link, _make_service(), locale="en")
        assert link in text_body

    def test_html_escapes_user_name(self):
        """HTML body escapes special characters in user names."""
        _, html_body, _ = email_messages.get_signup_confirmation_email(
            "<img src=x>",
            "https://example.com/verify",
            _make_service(),
            locale="en",
        )
        # Check that the user name is properly escaped in the greeting
        # (after the logo img tag which is legitimate)
        greeting_section = html_body.split("<h3")[1]
        assert "<img src=x>" not in greeting_section
        assert "&lt;img src=x&gt;" in greeting_section

    def test_plain_text_does_not_escape_user_name(self):
        """Plain-text body keeps the raw user name without HTML escaping."""
        name = "O'Brien & Co"
        _, _, text_body = email_messages.get_signup_confirmation_email(
            name,
            "https://example.com/verify",
            _make_service(),
            locale="en",
        )
        assert "O'Brien & Co" in text_body

    def test_unknown_locale_falls_back_to_english(self):
        """Unsupported locale falls back to English subject."""
        subject_xx, _, _ = email_messages.get_signup_confirmation_email(
            "Alice",
            "https://example.com/verify",
            _make_service(),
            locale="xx",
        )
        subject_us, _, _ = email_messages.get_signup_confirmation_email(
            "Alice",
            "https://example.com/verify",
            _make_service(),
            locale="en",
        )
        assert subject_xx == subject_us


class TestGetAdminSignupNotificationEmail:
    """Tests for get_admin_signup_notification_email."""

    def test_returns_three_tuple(self):
        """Builder returns (subject, html, text) tuple."""
        result = email_messages.get_admin_signup_notification_email(
            "Admin",
            "New User",
            "newuser",
            _make_service(),
            locale="en",
        )
        assert len(result) == 3

    def test_html_contains_new_user_name(self):
        """HTML body contains the new user's display name."""
        _, html_body, _ = email_messages.get_admin_signup_notification_email(
            "Admin",
            "New User",
            "newuser",
            _make_service(),
            locale="en",
        )
        assert "New User" in html_body

    def test_admin_link_url_encodes_username(self):
        """Admin link URL-encodes special characters in username."""
        _, html_body, _ = email_messages.get_admin_signup_notification_email(
            "Admin",
            "Some User",
            "user name@test",
            _make_service(),
            locale="en",
        )
        # The raw username with spaces/@ must not appear unencoded in the link
        assert "user name@test" not in html_body

    def test_admin_link_html_escaped(self):
        """Admin link is HTML-escaped so attributes are not broken."""
        _, html_body, _ = email_messages.get_admin_signup_notification_email(
            "Admin",
            "Some User",
            "normaluser",
            _make_service(),
            locale="en",
        )
        # The link should contain the frontend host (escaped)
        assert "endurain.example.com" in html_body

    def test_html_escapes_sign_up_user_name(self):
        """HTML body escapes special characters in the new user name."""
        _, html_body, _ = email_messages.get_admin_signup_notification_email(
            "Admin",
            "<script>evil</script>",
            "eviluser",
            _make_service(),
            locale="en",
        )
        assert "<script>" not in html_body

    def test_html_escapes_admin_name_with_script_tag(self):
        """
        HTML body escapes <script> tags in the admin recipient name.

        Both `user_name` (admin) and `sign_up_user_name` pass through
        html.escape(); this test specifically validates that a
        malicious admin name cannot inject raw HTML.
        """
        _, html_body, _ = email_messages.get_admin_signup_notification_email(
            "<script>alert(1)</script>",
            "New User",
            "newuser",
            _make_service(),
            locale="en",
        )
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_uses_admin_locale_not_new_user_locale(self, monkeypatch, tmp_path):
        """Different admin locales produce different subjects."""
        import json as _json

        import core.i18n as core_i18n

        for code, subj in (("en", "EN subj"), ("pt-PT", "PT subj")):
            (tmp_path / code).mkdir()
            (tmp_path / code / "email.json").write_text(
                _json.dumps({"admin_signup.subject": subj}),
                encoding="utf-8",
            )
        monkeypatch.setattr(core_i18n, "_LOCALES_DIR", tmp_path)
        core_i18n._load_catalog.cache_clear()
        try:
            subject_pt, _, _ = email_messages.get_admin_signup_notification_email(
                "Admin",
                "New User",
                "newuser",
                _make_service(),
                locale="pt-PT",
            )
            subject_us, _, _ = email_messages.get_admin_signup_notification_email(
                "Admin",
                "New User",
                "newuser",
                _make_service(),
                locale="en",
            )
        finally:
            core_i18n._load_catalog.cache_clear()
        assert subject_pt != subject_us


class TestGetUserSignupApprovedEmail:
    """Tests for get_user_signup_approved_email."""

    def test_returns_three_tuple(self):
        """Builder returns (subject, html, text) tuple."""
        result = email_messages.get_user_signup_approved_email(
            "Alice",
            "alice99",
            _make_service(),
            locale="en",
        )
        assert len(result) == 3

    def test_html_contains_username(self):
        """HTML body contains the username."""
        _, html_body, _ = email_messages.get_user_signup_approved_email(
            "Alice",
            "alice99",
            _make_service(),
            locale="en",
        )
        assert "alice99" in html_body

    def test_html_contains_login_link(self):
        """HTML body includes a link to the login page."""
        _, html_body, _ = email_messages.get_user_signup_approved_email(
            "Alice",
            "alice99",
            _make_service(),
            locale="en",
        )
        assert "/login" in html_body

    def test_html_escapes_username(self):
        """HTML body escapes special characters in username."""
        _, html_body, _ = email_messages.get_user_signup_approved_email(
            "Alice",
            "<script>",
            _make_service(),
            locale="en",
        )
        assert "<script>" not in html_body

    def test_html_lang_es(self):
        """HTML uses 'es-ES' lang tag for Spanish locale."""
        _, html_body, _ = email_messages.get_user_signup_approved_email(
            "Alice",
            "alice99",
            _make_service(),
            locale="es",
        )
        assert 'lang="es-ES"' in html_body
