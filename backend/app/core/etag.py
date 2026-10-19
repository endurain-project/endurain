"""HTTP entity tags for optimistic concurrency.

``PATCH`` without a precondition is last-writer-wins: two clients that both read
an activity and both save will each succeed, and the first edit is silently gone
— no error, no trace, and the user who lost it has no way to know. With the app
open in two tabs, or on a phone and a laptop, that is ordinary use rather than a
race.

An ``If-Match`` header makes the write conditional on the version the client
actually saw. The version travels as an ETag, which is the standard HTTP
mechanism for exactly this and needs no bespoke field in every payload.
"""

import core.exceptions as core_exceptions

# The header a client echoes back from a previous response to make its write
# conditional (RFC 9110 §13.1.1).
IF_MATCH_HEADER = "If-Match"

# Matches any current representation. RFC 9110 requires servers to honour it, and
# it is how a client says "create-or-overwrite, I don't care which version".
_WILDCARD = "*"


def format_etag(version: int) -> str:
    """Render a row version as a strong ETag.

    Args:
        version: The row's optimistic-concurrency counter.

    Returns:
        The quoted entity tag, e.g. ``'"7"'``.
    """
    return f'"{version}"'


def parse_if_match(header: str) -> set[str]:
    """Parse an ``If-Match`` header into the set of tags it accepts.

    Args:
        header: The raw header value, which may be a comma-separated list.

    Returns:
        The tags, unquoted and with any weak-comparison prefix removed.
    """
    tags = set()
    for candidate in header.split(","):
        tag = candidate.strip()
        if tag.startswith("W/"):
            tag = tag[2:]
        tags.add(tag.strip('"'))
    return tags


def require_if_match(header: str | None, current_version: int | None) -> None:
    """Enforce an ``If-Match`` precondition against the stored version.

    A missing header is allowed: requiring it would break every existing client
    at once. Sending a *stale* one is the case worth rejecting, because that is a
    client that believes it is editing something it is not.

    Args:
        header: The request's ``If-Match`` value, if any.
        current_version: The stored row's version.

    Returns:
        None.

    Raises:
        PreconditionFailedError: When the header names a version that is not the
            current one.
    """
    if header is None:
        return
    accepted = parse_if_match(header)
    if _WILDCARD in accepted:
        return
    if current_version is None or str(current_version) not in accepted:
        raise core_exceptions.PreconditionFailedError("The activity was modified by someone else; re-read it and retry")
