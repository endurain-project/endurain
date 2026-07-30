"""The one paginated-list envelope every module returns.

A list endpoint returns this instead of a bare array, so a client can render
"showing 25 of 340" and decide whether a next page exists from the response it
already has. The alternative — a bare array plus a separate ``/count`` call —
costs two round trips, makes the client repeat its filters, and lets the count
disagree with the list it describes.

It is generic and lives in ``core`` rather than being redefined per module
because the shape is not a fact about any one domain, and two modules inventing
slightly different envelopes is exactly the drift a shared type prevents. Each
module aliases it for its own item type (e.g. ``ActivityPage = Page[Activity]``),
which keeps the call sites readable and gives the generated OpenAPI client a
concrete component per resource.
"""

import base64
import binascii
from datetime import datetime
from typing import Self

from pydantic import BaseModel

import core.exceptions as core_exceptions

#: Default page size for a *browse* list (activities, followers) when the request
#: omits pagination. Declared here so the routers stop each keeping a private
#: copy of the same two numbers.
DEFAULT_NUM_RECORDS = 25

#: Hard cap on the client-requested page size, bounding query and serialization
#: cost per request (defense against resource exhaustion).
MAX_NUM_RECORDS = 200

#: Default page size for an activity's *child* collections (laps, sets, workout
#: steps). Unlike a browse list these are "everything hanging off one parent",
#: which a client almost always wants in full, so the default is the cap rather
#: than a small window — the parameter exists to bound the response, not to make
#: the common read a multi-page walk.
DEFAULT_CHILD_NUM_RECORDS = MAX_NUM_RECORDS


class Page[ItemT](BaseModel):
    """One page of results plus everything needed to paginate.

    Attributes:
        items: The records on this page.
        total: Total matching records across all pages, carrying the same filters
            and the same access scoping as ``items``.
        page: The 1-based page number these items came from.
        num_records: The page size used.
        next: The next page number, or ``None`` when this is the last page.
    """

    items: list[ItemT]
    total: int
    page: int
    num_records: int
    next: int | None = None

    @classmethod
    def build(
        cls,
        items: list[ItemT] | None,
        total: int,
        page: int,
        num_records: int,
    ) -> Self:
        """Assemble a page, deriving ``next`` from the totals.

        Deriving ``next`` server-side is what stops every client reimplementing
        the same page arithmetic (and getting the final page wrong).

        Args:
            items: The records on this page (``None`` is treated as empty, so a
                CRUD layer that returns ``None`` for "no rows" needs no special
                casing at the call site).
            total: Total matching records across all pages.
            page: The 1-based page number.
            num_records: The page size.

        Returns:
            The populated page envelope.
        """
        rows = items or []
        return cls(
            items=rows,
            total=total,
            page=page,
            num_records=num_records,
            next=page + 1 if page * num_records < total else None,
        )


# --- Keyset pagination -------------------------------------------------------
#
# Offset pagination is wrong for any list that grows at the head. Between a
# client's page 1 and page 2, a newly inserted row shifts every later row down
# one, so the client sees the boundary row twice and never sees whatever it
# displaced. The following feed receives inserts continuously, which makes that
# the normal case rather than a race. A keyset cursor names the last row seen
# instead of counting how many to discard, so concurrent inserts cannot shift
# the window. It also drops the ``COUNT(*)`` and the ``OFFSET n`` scan.

# Separates the two cursor components. Neither an ISO-8601 timestamp nor an
# integer id can contain it, so no escaping is needed.
_CURSOR_SEPARATOR = "|"


class CursorPage[ItemT](BaseModel):
    """One keyset-paginated slice plus the cursor for the next one.

    Deliberately carries no ``total``: producing one costs a second aggregate
    query over the whole filtered set on every request, and for a feed it is
    stale before the client renders it.

    Attributes:
        items: The records in this slice, newest first.
        num_records: The page size used.
        next_cursor: Opaque cursor for the following slice, or ``None`` when the
            end has been reached.
    """

    items: list[ItemT]
    num_records: int
    next_cursor: str | None = None


def encode_cursor(sort_value: datetime, tiebreak_id: int) -> str:
    """Encode a keyset position into an opaque cursor.

    The cursor is base64url of ``{sort_value}|{id}``. It is opaque rather than
    signed because it cannot widen access: the rows a caller may see are derived
    from their own identity on every request, so a forged cursor only moves the
    window inside a result set they were already entitled to.

    Args:
        sort_value: The sort column of the last row in the slice.
        tiebreak_id: That row's id, disambiguating equal sort values.

    Returns:
        The encoded cursor.
    """
    raw = f"{sort_value.isoformat()}{_CURSOR_SEPARATOR}{tiebreak_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    """Decode an opaque cursor back into a keyset position.

    Args:
        cursor: A cursor previously produced by :func:`encode_cursor`.

    Returns:
        The ``(sort_value, id)`` pair the cursor encodes.

    Raises:
        InvalidInputError: When the cursor is not one this server issued.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        sort_value, _, tiebreak_id = raw.rpartition(_CURSOR_SEPARATOR)
        return datetime.fromisoformat(sort_value), int(tiebreak_id)
    except (ValueError, UnicodeDecodeError, binascii.Error) as err:
        raise core_exceptions.InvalidInputError("Invalid pagination cursor") from err
