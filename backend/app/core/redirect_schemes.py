"""The URI schemes a redirect after sign-in must never use.

Shared by the ``ALLOWED_REDIRECT_SCHEMES`` and ``ALLOWED_REDIRECT_URIS`` settings, which refuse them at startup, and the redirect validator,
which refuses them even when they are configured. It reads no settings, so a pure layer may import it.
"""


def normalise_redirect_uri(uri: str) -> str:
    """Return a ``scheme://rest`` address with its scheme lower-cased; the rest is kept exactly as written."""
    scheme, separator, rest = uri.partition("://")
    return f"{scheme.lower()}{separator}{rest}"


#: ``http`` and ``https`` are external redirects; the rest run script or read local content in the browser.
UNSAFE_REDIRECT_SCHEMES = frozenset({"http", "https", "javascript", "data", "file", "vbscript", "blob"})
