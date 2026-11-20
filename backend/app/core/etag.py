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

import re
from collections.abc import Callable, Generator
from contextlib import contextmanager

from fastapi import Response
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

# The header a client echoes back from a previous response to make its write
# conditional (RFC 9110 §13.1.1).
IF_MATCH_HEADER = "If-Match"

# Matches any current representation. RFC 9110 requires servers to honour it, and
# it is how a client says "create-or-overwrite, I don't care which version".
WILDCARD = "*"

# One element of an RFC 9110 §5.6.1 list of entity tags (§8.8.3: entity-tag = [ "W/" ] DQUOTE *etagc DQUOTE,
# etagc = %x21 / %x23-7E / obs-text): optional whitespace, an optional tag, then a comma or the end. Elements may be
# empty. The quantifiers are possessive, so a long malformed header is refused in linear time.
_LIST_ELEMENT = re.compile(r'[ \t]*+(?:(W/)?+"([\x21\x23-\x7e\x80-\xff]*+)"[ \t]*+)?+(?:(,)|\Z)')


def format_etag(version: int) -> str:
    """Render a row version as a strong ETag.

    Args:
        version: The row's optimistic-concurrency counter.

    Returns:
        The quoted entity tag, e.g. ``'"7"'``.
    """
    return f'"{version}"'


def set_etag(response: Response, version: int) -> None:
    """Send a row version as the response's ``ETag``, the tag a client echoes in ``If-Match``.

    Args:
        response: The response the route returns.
        version: The row's optimistic-concurrency counter.
    """
    response.headers["ETag"] = format_etag(version)


def is_wildcard(header: str) -> bool:
    """Return whether an ``If-Match`` header is the wildcard, which matches any current version.

    Args:
        header: The raw header value.

    Returns:
        True when the header is ``*`` alone; a quoted ``"*"`` is an ordinary entity tag.
    """
    return header.strip(" \t") == WILDCARD


def parse_if_match(header: str) -> set[str]:
    """Parse an ``If-Match`` list of entity tags into the set of tags it accepts.

    Args:
        header: The raw header value, a comma-separated list of quoted entity tags. The wildcard
            is checked first with :func:`is_wildcard`.

    Returns:
        The opaque values of the strong tags. Weak tags (``W/"7"``) are left out: ``If-Match``
        requires strong comparison (RFC 9110 §13.1.1), so a weak tag never matches. An empty
        list matches no version.

    Raises:
        InvalidInputError: When the header is not a list of quoted entity tags (``If-Match: 7``),
            which is a malformed request rather than a stale one.
    """
    tags = set()
    position = 0
    while True:
        element = _LIST_ELEMENT.match(header, position)
        if element is None:
            raise core_exceptions.InvalidInputError('If-Match must be a list of quoted entity tags, such as "3"')
        weak, tag, separator = element.groups()
        if tag is not None and weak is None:
            tags.add(tag)
        if separator is None:
            return tags
        position = element.end()


def matches_if_none_match(header: str | None, version: int) -> bool:
    """Return whether an ``If-None-Match`` header names the current version.

    Weak comparison applies (RFC 9110 §13.1.2), so a ``W/`` prefix, which proxies add, still
    matches, as does ``*``.

    Args:
        header: The request's ``If-None-Match`` value, if any.
        version: The stored row's version.

    Returns:
        True when the client's cached copy is current.
    """
    if header is None:
        return False
    tags = {candidate.strip().removeprefix("W/").strip('"') for candidate in header.split(",")}
    return WILDCARD in tags or str(version) in tags


def require_if_match(header: str, current_version: int | None, resource: str) -> None:
    """Enforce an ``If-Match`` precondition against the stored version.

    The header is required by the route (see ``core.dependencies.IfMatch``), so a stale one is
    the case left to reject: a client that believes it is editing something it is not.

    Args:
        header: The request's ``If-Match`` value.
        current_version: The stored row's version.
        resource: What the row is, named in the refusal message.

    Returns:
        None.

    Raises:
        InvalidInputError: When the header is not ``*`` or a list of quoted entity tags.
        PreconditionFailedError: When the header names a version that is not the
            current one.
    """
    if is_wildcard(header):
        return
    accepted = parse_if_match(header)
    if current_version is None or str(current_version) not in accepted:
        raise core_exceptions.PreconditionFailedError(
            f"The {resource} was modified by someone else; re-read it and retry"
        )


@contextmanager
def refuse_stale_write(
    db: Session, resource: str, still_exists: Callable[[], bool], not_found_message: str
) -> Generator[None]:
    """Turn a write that lost the version race at flush time into a refusal.

    Args:
        db: Database session, rolled back when the race was lost.
        resource: What the row is, named in the refusal message.
        still_exists: Reads, after the rollback, whether the row can still be found.
        not_found_message: The message when the row was deleted meanwhile.

    Yields:
        None; the guarded block is the write and, where the caller needs it, the commit.

    Raises:
        NotFoundError: When the row is gone.
        PreconditionFailedError: When the row changed since the client read it.
    """
    try:
        yield
    except StaleDataError as err:
        db.rollback()
        if not still_exists():
            raise core_exceptions.NotFoundError(not_found_message) from err
        logger.debug("Rejected a stale write", extra=core_logger.context(resource=resource))
        raise core_exceptions.PreconditionFailedError(
            f"The {resource} was modified by someone else; re-read it and retry"
        ) from err
