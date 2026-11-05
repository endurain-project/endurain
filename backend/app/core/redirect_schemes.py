"""The URI schemes a redirect after sign-in must never use.

Shared by the ``ALLOWED_REDIRECT_SCHEMES`` setting, which refuses them at startup, and the redirect validator,
which refuses them even when they are configured. It reads no settings, so a pure layer may import it.
"""

#: ``http`` and ``https`` are external redirects; the rest run script or read local content in the browser.
UNSAFE_REDIRECT_SCHEMES = frozenset({"http", "https", "javascript", "data", "file", "vbscript", "blob"})
