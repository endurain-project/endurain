"""
Sanitization utilities for user-generated content.

Provides functions to sanitize markdown and HTML content
to prevent XSS attacks while preserving safe formatting.

Backed by ``nh3`` (Rust ``ammonia``) rather than ``bleach``, which is
unmaintained. Beyond maintenance, ``nh3`` validates attribute *values* and not
only their names: ``bleach`` let ``<a href="javascript:...">`` through, because
``href`` was on the allowed-attribute list regardless of the scheme it carried.
:data:`ALLOWED_URL_SCHEMES` is the explicit allowlist that replaces it.
"""

import nh3

# Allowed HTML tags for markdown content
ALLOWED_TAGS = {
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
}

# Allowed HTML attributes for markdown content. ``rel`` is deliberately absent:
# ``link_rel`` below sets it on every link, and nh3 refuses to let a document
# also supply its own so the guard cannot be overridden from the content.
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "target"},
}

# URL schemes an ``href`` may carry. Anything else — ``javascript:``, ``data:``,
# ``vbscript:``, ``file:`` — has the attribute dropped.
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}

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

    return nh3.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )


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
    return nh3.clean(content, tags=set(), attributes={})


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

    return nh3.clean(
        content,
        tags={"a"},
        attributes={"a": {"href", "title", "target"}},
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
