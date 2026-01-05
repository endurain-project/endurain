"""
Sanitization utilities for user-generated content.

Provides functions to sanitize markdown and HTML content
to prevent XSS attacks while preserving safe formatting.
"""

import bleach


# Allowed HTML tags for markdown content
ALLOWED_TAGS = [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "hr",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "pre",
    "strong",
    "em",
    "del",
    "a",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]

# Allowed HTML attributes for markdown content
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}

# Maximum length for markdown fields
MAX_MARKDOWN_LENGTH = 2500


def sanitize_markdown(content: str | None) -> str | None:
    """
    Sanitize markdown content to prevent XSS attacks.

    Strips dangerous HTML tags and attributes while preserving
    safe markdown formatting elements.

    Args:
        content: The raw markdown/HTML content to sanitize.

    Returns:
        Sanitized content safe for storage and display,
        or None if input is None.
    """
    if content is None:
        return None

    if not isinstance(content, str):
        return None

    # Strip content that exceeds max length
    content = content[:MAX_MARKDOWN_LENGTH]

    # Use bleach to sanitize HTML/markdown content
    sanitized = bleach.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )

    return sanitized


def sanitize_plain_text(content: str | None) -> str | None:
    """
    Sanitize plain text content by stripping all HTML.

    Args:
        content: The raw text content to sanitize.

    Returns:
        Sanitized plain text with all HTML removed,
        or None if input is None.
    """
    if content is None:
        return None

    if not isinstance(content, str):
        return None

    # Strip all HTML tags
    sanitized = bleach.clean(content, tags=[], strip=True)

    return sanitized


def sanitize_attribution(content: str | None) -> str | None:
    """
    Sanitize attribution text to prevent XSS attacks.

    Allows only <a> tags with safe attributes for
    attribution links.

    Args:
        content: Raw attribution string.

    Returns:
        Sanitized string with only safe HTML,
        or None if input is None.
    """
    if content is None:
        return None

    if not isinstance(content, str):
        return None

    # Use bleach to sanitize - only allow <a> tags
    sanitized = bleach.clean(
        content,
        tags=["a"],
        attributes={"a": ["href", "title", "target", "rel"]},
        strip=True,
    )

    return sanitized
