"""The URI schemes a redirect after sign-in must never use, and how a redirect's scheme is read.

Shared by the ``ALLOWED_REDIRECT_SCHEMES`` and ``ALLOWED_REDIRECT_URIS`` settings, which refuse them at startup, and the redirect validator,
which refuses them even when they are configured. It reads no settings, so a pure layer may import it.
"""

import re

#: RFC 3986 3.1: ``scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )``.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")

#: ``http`` and ``https`` are external redirects; the rest run script or read local content in the browser.
UNSAFE_REDIRECT_SCHEMES = frozenset({"http", "https", "javascript", "data", "file", "vbscript", "blob"})


def uri_scheme(uri: str) -> str | None:
    """Return the lower-cased scheme of an absolute URI, or None when the value has no scheme.

    The scheme runs up to the first ``:`` (RFC 3986 3.1), so ``app:/callback`` and ``app://callback`` both have the
    scheme ``app``. A value starting with ``/`` never has one, because a scheme starts with a letter.

    Args:
        uri: The value to read.

    Returns:
        The scheme in lower case, or None.
    """
    scheme, separator, _ = uri.partition(":")
    if not separator or not _SCHEME.fullmatch(scheme):
        return None
    return scheme.lower()


def normalise_redirect_uri(uri: str) -> str:
    """Return an address with its scheme lower-cased and the rest kept exactly as written.

    Args:
        uri: The address to normalise.

    Returns:
        The address in the form in which redirect addresses are compared, or the value unchanged when it has no scheme.
    """
    scheme = uri_scheme(uri)
    return uri if scheme is None else scheme + uri[len(scheme) :]
