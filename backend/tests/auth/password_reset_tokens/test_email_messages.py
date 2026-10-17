"""Tests for password reset email message builders."""

from unittest.mock import MagicMock

import modules.auth.password_reset_tokens.email_messages as email_messages


def _make_service(frontend_host: str = "https://endurain.example.com"):
    """Build a minimal AppriseService mock."""
    svc = MagicMock()
    svc.frontend_host = frontend_host
    return svc


class TestGetPasswordResetEmail:
    """Tests for get_password_reset_email."""

    def test_returns_three_tuple(self):
        """Builder returns (subject, html, text) tuple."""
        result = email_messages.get_password_reset_email(
            "Alice",
            "https://example.com/reset?token=abc",
            _make_service(),
            locale="en",
        )
        assert len(result) == 3

    def test_subject_contains_endurain(self):
        """Subject line contains 'Endurain'."""
        subject, _, _ = email_messages.get_password_reset_email(
            "Alice",
            "https://example.com/reset?token=abc",
            _make_service(),
            locale="en",
        )
        assert "Endurain" in subject

    def test_html_contains_reset_link(self):
        """HTML body contains the reset link."""
        link = "https://example.com/reset?token=abc"
        _, html_body, _ = email_messages.get_password_reset_email("Alice", link, _make_service(), locale="en")
        assert link in html_body

    def test_text_contains_reset_link(self):
        """Plain-text body contains the reset link."""
        link = "https://example.com/reset?token=abc"
        _, _, text_body = email_messages.get_password_reset_email("Alice", link, _make_service(), locale="en")
        assert link in text_body

    def test_html_lang_attribute_en_us(self):
        """HTML body uses lang='en-US' for the 'en' locale."""
        _, html_body, _ = email_messages.get_password_reset_email(
            "Alice",
            "https://example.com/reset",
            _make_service(),
            locale="en",
        )
        assert 'lang="en-US"' in html_body

    def test_html_lang_attribute_pt(self):
        """HTML body uses lang='pt-PT' for the 'pt-PT' locale."""
        _, html_body, _ = email_messages.get_password_reset_email(
            "Alice",
            "https://example.com/reset",
            _make_service(),
            locale="pt-PT",
        )
        assert 'lang="pt-PT"' in html_body

    def test_unknown_locale_falls_back_to_english(self):
        """Unknown locale falls back to English content."""
        subject_xx, _, _ = email_messages.get_password_reset_email(
            "Bob",
            "https://example.com/reset",
            _make_service(),
            locale="xx",
        )
        subject_us, _, _ = email_messages.get_password_reset_email(
            "Bob",
            "https://example.com/reset",
            _make_service(),
            locale="en",
        )
        assert subject_xx == subject_us

    def test_none_locale_falls_back_to_english(self):
        """None locale falls back to English content."""
        subject_none, _, _ = email_messages.get_password_reset_email(
            "Bob",
            "https://example.com/reset",
            _make_service(),
            locale=None,
        )
        subject_us, _, _ = email_messages.get_password_reset_email(
            "Bob",
            "https://example.com/reset",
            _make_service(),
            locale="en",
        )
        assert subject_none == subject_us

    def test_html_escapes_user_name(self):
        """HTML body escapes special characters in user names."""
        _, html_body, _ = email_messages.get_password_reset_email(
            "<script>alert(1)</script>",
            "https://example.com/reset",
            _make_service(),
            locale="en",
        )
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_plain_text_does_not_escape_user_name(self):
        """Plain-text body keeps the raw user name without escaping."""
        name = "Alice & Bob"
        _, _, text_body = email_messages.get_password_reset_email(
            name,
            "https://example.com/reset",
            _make_service(),
            locale="en",
        )
        assert "Alice & Bob" in text_body

    def test_html_escapes_attribute_breaking_name(self):
        """
        HTML body neutralises attribute-breaking injection in name.

        Tests a different XSS vector: a payload that attempts to
        break out of an HTML attribute context using a quote
        followed by an event-handler tag.

        html.escape escapes '<' and '>' (breaking the tag boundary)
        so 'onerror=alert(1)' may appear as harmless plain text
        inside the entity-escaped string; the important guarantee
        is that no raw '<img' tag is injected into the DOM.
        """
        malicious = '"><img src=x onerror=alert(1)>'
        _, html_body, _ = email_messages.get_password_reset_email(
            malicious,
            "https://example.com/reset",
            _make_service(),
            locale="en",
        )
        # The '<' of '<img' must be escaped to '&lt;'
        # so the raw tag boundary is never present.
        assert "<img src=x" not in html_body
        assert "&lt;img src=x" in html_body

    def test_pt_subject_differs_from_us(self, monkeypatch, tmp_path):
        """Translated catalogs produce locale-specific subjects."""
        # Drive the test off isolated on-disk catalogs so we do not
        # depend on which non-default catalogs ship with the repo.
        import json as _json

        import core.i18n as core_i18n

        for code, subj in (("en", "EN subject"), ("pt-PT", "PT subject")):
            (tmp_path / code).mkdir()
            (tmp_path / code / "email.json").write_text(
                _json.dumps({"password_reset.subject": subj}),
                encoding="utf-8",
            )
        monkeypatch.setattr(core_i18n, "_LOCALES_DIR", tmp_path)
        core_i18n._load_catalog.cache_clear()
        try:
            subject_us, _, _ = email_messages.get_password_reset_email(
                "Alice",
                "https://example.com/reset",
                _make_service(),
                locale="en",
            )
            subject_pt, _, _ = email_messages.get_password_reset_email(
                "Alice",
                "https://example.com/reset",
                _make_service(),
                locale="pt-PT",
            )
        finally:
            core_i18n._load_catalog.cache_clear()
        assert subject_us != subject_pt
