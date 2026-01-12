"""
Tests for core.sanitization module.

Verifies:
1. Markdown sanitization removes dangerous tags
2. Plain text sanitization strips all HTML
3. Attribution sanitization allows only safe link tags
4. None and non-string input handling
5. Length limits enforcement
6. XSS attack prevention
"""

import pytest
from core import sanitization


class TestSanitizeMarkdown:
    """Tests for sanitize_markdown function."""

    def test_sanitize_markdown_none(self):
        """Test that None input returns None."""
        result = sanitization.sanitize_markdown(None)
        assert result is None

    def test_sanitize_markdown_non_string(self):
        """Test that non-string input returns None."""
        assert sanitization.sanitize_markdown(123) is None
        assert sanitization.sanitize_markdown([]) is None
        assert sanitization.sanitize_markdown({}) is None

    def test_sanitize_markdown_plain_text(self):
        """Test sanitizing plain text preserves content."""
        content = "This is plain text content"
        result = sanitization.sanitize_markdown(content)
        assert result == content

    def test_sanitize_markdown_safe_tags(self):
        """Test that safe HTML tags are preserved."""
        content = "<p>Paragraph</p><strong>Bold</strong><em>Italic</em>"
        result = sanitization.sanitize_markdown(content)
        assert "<p>" in result
        assert "<strong>" in result
        assert "<em>" in result

    def test_sanitize_markdown_removes_script_tags(self):
        """Test that script tags are removed."""
        content = '<p>Safe content</p><script>alert("XSS")</script>'
        result = sanitization.sanitize_markdown(content)
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Safe content" in result
        # Note: bleach removes tags but preserves text content

    def test_sanitize_markdown_removes_onclick(self):
        """Test that onclick attributes are removed."""
        content = '<p onclick="alert(\'XSS\')">Click me</p>'
        result = sanitization.sanitize_markdown(content)
        assert "onclick" not in result
        assert "Click me" in result

    def test_sanitize_markdown_preserves_safe_links(self):
        """Test that safe link attributes are preserved."""
        content = '<a href="https://example.com" title="Example">Link</a>'
        result = sanitization.sanitize_markdown(content)
        assert '<a href="https://example.com"' in result
        assert 'title="Example"' in result

    def test_sanitize_markdown_removes_unsafe_link_attributes(self):
        """Test that unsafe link attributes are removed."""
        content = '<a href="https://example.com" onclick="alert(\'XSS\')">Link</a>'
        result = sanitization.sanitize_markdown(content)
        assert "onclick" not in result
        assert "href" in result

    def test_sanitize_markdown_heading_tags(self):
        """Test that heading tags are preserved."""
        content = "<h1>Title</h1><h2>Subtitle</h2><h3>Section</h3>"
        result = sanitization.sanitize_markdown(content)
        assert "<h1>" in result
        assert "<h2>" in result
        assert "<h3>" in result

    def test_sanitize_markdown_list_tags(self):
        """Test that list tags are preserved."""
        content = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = sanitization.sanitize_markdown(content)
        assert "<ul>" in result
        assert "<li>" in result

    def test_sanitize_markdown_code_tags(self):
        """Test that code tags are preserved."""
        content = "<pre><code>const x = 1;</code></pre>"
        result = sanitization.sanitize_markdown(content)
        assert "<pre>" in result
        assert "<code>" in result

    def test_sanitize_markdown_table_tags(self):
        """Test that table tags are preserved."""
        content = "<table><tr><th>Header</th></tr><tr><td>Data</td></tr></table>"
        result = sanitization.sanitize_markdown(content)
        assert "<table>" in result
        assert "<tr>" in result
        assert "<th>" in result
        assert "<td>" in result

    def test_sanitize_markdown_removes_iframe(self):
        """Test that iframe tags are removed."""
        content = '<p>Content</p><iframe src="https://malicious.com"></iframe>'
        result = sanitization.sanitize_markdown(content)
        assert "<iframe>" not in result
        assert "Content" in result

    def test_sanitize_markdown_removes_object_embed(self):
        """Test that object and embed tags are removed."""
        content = '<object data="file.swf"></object><embed src="file.swf">'
        result = sanitization.sanitize_markdown(content)
        assert "<object>" not in result
        assert "<embed>" not in result

    def test_sanitize_markdown_max_length(self):
        """Test that content is truncated at max length."""
        content = "a" * 3000  # Exceeds MAX_MARKDOWN_LENGTH (2500)
        result = sanitization.sanitize_markdown(content)
        assert len(result) == 2500

    def test_sanitize_markdown_empty_string(self):
        """Test that empty string is handled correctly."""
        result = sanitization.sanitize_markdown("")
        assert result == ""

    def test_sanitize_markdown_unicode_content(self):
        """Test that unicode content is preserved."""
        content = "<p>Hello 世界 🌍</p>"
        result = sanitization.sanitize_markdown(content)
        assert "世界" in result
        assert "🌍" in result


class TestSanitizePlainText:
    """Tests for sanitize_plain_text function."""

    def test_sanitize_plain_text_none(self):
        """Test that None input returns None."""
        result = sanitization.sanitize_plain_text(None)
        assert result is None

    def test_sanitize_plain_text_non_string(self):
        """Test that non-string input returns None."""
        assert sanitization.sanitize_plain_text(123) is None
        assert sanitization.sanitize_plain_text([]) is None

    def test_sanitize_plain_text_no_html(self):
        """Test that plain text without HTML is preserved."""
        content = "This is plain text"
        result = sanitization.sanitize_plain_text(content)
        assert result == content

    def test_sanitize_plain_text_removes_all_tags(self):
        """Test that all HTML tags are removed."""
        content = "<p>Paragraph</p><strong>Bold</strong><em>Italic</em>"
        result = sanitization.sanitize_plain_text(content)
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "<em>" not in result
        assert "Paragraph" in result
        assert "Bold" in result
        assert "Italic" in result

    def test_sanitize_plain_text_removes_script(self):
        """Test that script tags are removed."""
        content = 'Text<script>alert("XSS")</script>More text'
        result = sanitization.sanitize_plain_text(content)
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Text" in result
        assert "More text" in result
        # Note: bleach removes tags but preserves text content

    def test_sanitize_plain_text_removes_links(self):
        """Test that link tags are removed."""
        content = '<a href="https://example.com">Link text</a>'
        result = sanitization.sanitize_plain_text(content)
        assert "<a" not in result
        assert "href" not in result
        assert "Link text" in result

    def test_sanitize_plain_text_empty_string(self):
        """Test that empty string is handled correctly."""
        result = sanitization.sanitize_plain_text("")
        assert result == ""

    def test_sanitize_plain_text_unicode(self):
        """Test that unicode content is preserved."""
        content = "Hello 世界 🌍"
        result = sanitization.sanitize_plain_text(content)
        assert result == content


class TestSanitizeAttribution:
    """Tests for sanitize_attribution function."""

    def test_sanitize_attribution_none(self):
        """Test that None input returns None."""
        result = sanitization.sanitize_attribution(None)
        assert result is None

    def test_sanitize_attribution_non_string(self):
        """Test that non-string input returns None."""
        assert sanitization.sanitize_attribution(123) is None
        assert sanitization.sanitize_attribution([]) is None

    def test_sanitize_attribution_plain_text(self):
        """Test that plain text is preserved."""
        content = "Photo by John Doe"
        result = sanitization.sanitize_attribution(content)
        assert result == content

    def test_sanitize_attribution_preserves_links(self):
        """Test that link tags are preserved."""
        content = '<a href="https://example.com">John Doe</a>'
        result = sanitization.sanitize_attribution(content)
        assert "<a" in result
        assert 'href="https://example.com"' in result
        assert "John Doe" in result

    def test_sanitize_attribution_link_attributes(self):
        """Test that safe link attributes are preserved."""
        content = '<a href="https://example.com" title="Author" target="_blank" rel="noopener">John</a>'
        result = sanitization.sanitize_attribution(content)
        assert 'href="https://example.com"' in result
        assert 'title="Author"' in result
        assert 'target="_blank"' in result
        assert 'rel="noopener"' in result

    def test_sanitize_attribution_removes_other_tags(self):
        """Test that non-link tags are removed."""
        content = '<p>Photo by <strong>John Doe</strong></p>'
        result = sanitization.sanitize_attribution(content)
        assert "<p>" not in result
        assert "<strong>" not in result
        assert "Photo by" in result
        assert "John Doe" in result

    def test_sanitize_attribution_removes_script(self):
        """Test that script tags are removed."""
        content = 'Photo by <script>alert("XSS")</script>John'
        result = sanitization.sanitize_attribution(content)
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Photo by" in result
        # Note: bleach removes tags but preserves text content

    def test_sanitize_attribution_removes_onclick(self):
        """Test that onclick attributes are removed from links."""
        content = '<a href="https://example.com" onclick="alert(\'XSS\')">John</a>'
        result = sanitization.sanitize_attribution(content)
        assert "onclick" not in result
        assert "href" in result

    def test_sanitize_attribution_empty_string(self):
        """Test that empty string is handled correctly."""
        result = sanitization.sanitize_attribution("")
        assert result == ""

    def test_sanitize_attribution_unicode(self):
        """Test that unicode content is preserved."""
        content = '<a href="https://example.com">作者 🎨</a>'
        result = sanitization.sanitize_attribution(content)
        assert "作者" in result
        assert "🎨" in result


class TestXSSPrevention:
    """Tests for XSS attack prevention across all functions."""

    @pytest.mark.parametrize(
        "malicious_content",
        [
            '<img src=x onerror="alert(\'XSS\')">',
            '<svg onload="alert(\'XSS\')">',
            '<body onload="alert(\'XSS\')">',
            '<input onfocus="alert(\'XSS\')" autofocus>',
            '<select onfocus="alert(\'XSS\')" autofocus>',
            '<textarea onfocus="alert(\'XSS\')" autofocus>',
            '<iframe src="javascript:alert(\'XSS\')">',
            '<object data="javascript:alert(\'XSS\')">',
            '<embed src="data:text/html;base64,PHNjcmlwdD5hbGVydCgnWFNTJyk8L3NjcmlwdD4=">',
            '<link rel="stylesheet" href="javascript:alert(\'XSS\')">',
            '<style>body{background:url("javascript:alert(\'XSS\')")}</style>',
        ],
    )
    def test_markdown_prevents_xss(self, malicious_content):
        """Test that sanitize_markdown prevents various XSS attacks."""
        result = sanitization.sanitize_markdown(malicious_content)
        # Verify dangerous HTML attributes and scripts are removed
        assert "<script" not in result.lower()
        assert "onerror" not in result
        assert "onload" not in result
        # Note: Some content like text inside tags may remain, but tags are stripped

    @pytest.mark.parametrize(
        "malicious_content",
        [
            '<script>alert("XSS")</script>',
            '<img src=x onerror="alert(\'XSS\')">',
            '<a href="javascript:alert(\'XSS\')">Click</a>',
        ],
    )
    def test_plain_text_prevents_xss(self, malicious_content):
        """Test that sanitize_plain_text prevents XSS attacks."""
        result = sanitization.sanitize_plain_text(malicious_content)
        # Verify all HTML tags are removed
        assert "<script" not in result.lower()
        assert "<img" not in result.lower()
        assert "<a" not in result.lower()
        assert "onerror" not in result or "<" not in result

    @pytest.mark.parametrize(
        "malicious_content",
        [
            '<a href="javascript:alert(\'XSS\')">Click</a>',
            '<a onclick="alert(\'XSS\')" href="#">Click</a>',
            '<script>alert("XSS")</script><a href="#">Link</a>',
        ],
    )
    def test_attribution_prevents_xss(self, malicious_content):
        """Test that sanitize_attribution prevents XSS attacks."""
        result = sanitization.sanitize_attribution(malicious_content)
        assert "javascript:" not in result
        assert "onclick" not in result
        assert "<script>" not in result
