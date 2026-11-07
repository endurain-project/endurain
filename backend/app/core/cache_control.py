"""The headers that keep a response carrying a secret out of every cache.

A token, a one-time key or code, or an archive of a user's data must not outlive the request in a
browser, proxy or shared cache. ``Cache-Control: no-store`` says so (RFC 9111 section 5.2.2.5) and
``Pragma: no-cache`` covers HTTP/1.0 caches.
"""

from fastapi import Response

#: The header pair, for a response that sets its own headers, such as a ``StreamingResponse``.
NO_STORE_HEADERS: dict[str, str] = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def set_no_store(response: Response) -> None:
    """Mark the response as one no cache may store.

    Args:
        response: The response the route returns.
    """
    response.headers.update(NO_STORE_HEADERS)
