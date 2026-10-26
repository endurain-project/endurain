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

from collections.abc import Callable, Generator
from contextlib import contextmanager

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
        The unquoted tags. Weak tags (``W/"7"``) are left out: ``If-Match`` requires strong
        comparison (RFC 9110 §13.1.1), so a weak tag never matches.
    """
    tags = set()
    for candidate in header.split(","):
        tag = candidate.strip()
        if not tag.startswith("W/"):
            tags.add(tag.strip('"'))
    return tags


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
        PreconditionFailedError: When the header names a version that is not the
            current one.
    """
    accepted = parse_if_match(header)
    if WILDCARD in accepted:
        return
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
        logger.warning("Rejected a stale write", extra=core_logger.context(resource=resource))
        raise core_exceptions.PreconditionFailedError(
            f"The {resource} was modified by someone else; re-read it and retry"
        ) from err
