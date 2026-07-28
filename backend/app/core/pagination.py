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

from typing import Self

from pydantic import BaseModel


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
