"""One paginated read of an activity's child collection, defined once.

Laps, sets and workout steps are the same read three times over: check the shared
:mod:`~modules.activities.activity.child_access` gate, page the rows, count them,
and wrap the two in the page envelope — with "refused" and "there are none"
deliberately answering the same way, so the endpoint cannot be used to probe
which activities exist.

Each of the three services held its own copy, ~98% identical after renaming the
resource. That is not merely repetitive: the copies had already drifted (the
refusal log lines differ), and the next divergence would be in the part that
decides what a non-owner may see. A child package now declares *what* it is —
its hide flag, its two CRUD calls, its page type — and this owns *how* the read
runs.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.child_access as activity_child_access

logger = core_logger.get_logger(__name__)


@dataclass(frozen=True)
class ChildCollection[PageT]:
    """A child collection's identity: what to read, and what guards it.

    Attributes:
        name: The resource in log messages (e.g. ``"laps"``).
        hide_attr: The parent activity's boolean ``hide_*`` flag guarding this
            child against a non-owner.
        fetch: Read one page of rows for an activity.
        count: Count an activity's rows.
        build: Wrap rows plus the total in the package's own page envelope.
    """

    name: str
    hide_attr: str
    fetch: Callable[..., list[Any]]
    count: Callable[[int, Session], int]
    build: Callable[[list[Any], int, int, int], PageT]

    def _empty(self, page_number: int, num_records: int) -> PageT:
        """Return the empty page — the answer to both "none" and "not allowed"."""
        return self.build([], 0, page_number, num_records)

    def _page(self, activity_id: int, db: Session, page_number: int, num_records: int) -> PageT:
        """Read one page and its total."""
        items = self.fetch(activity_id, db, page_number=page_number, num_records=num_records)
        return self.build(items, self.count(activity_id, db), page_number, num_records)

    def list_for_requester(
        self,
        activity_id: int,
        requester_user_id: int,
        db: Session,
        *,
        page_number: int,
        num_records: int,
    ) -> PageT:
        """Return one page for an authenticated caller.

        Args:
            activity_id: The parent activity.
            requester_user_id: The authenticated caller.
            db: Database session.
            page_number: 1-based page number.
            num_records: Page size.

        Returns:
            The page envelope, empty when the caller may not read this child.
        """
        if not activity_child_access.may_read_child(activity_id, requester_user_id, db, hide_attr=self.hide_attr):
            logger.debug(
                "Refused an activity child read; answering with an empty page",
                extra=core_logger.context(
                    activity_id=activity_id,
                    requester_user_id=requester_user_id,
                    child=self.name,
                ),
            )
            return self._empty(page_number, num_records)
        return self._page(activity_id, db, page_number, num_records)

    def list_public(
        self,
        activity_id: int,
        db: Session,
        *,
        page_number: int,
        num_records: int,
    ) -> PageT:
        """Return one page for an anonymous caller.

        Args:
            activity_id: The parent activity.
            db: Database session.
            page_number: 1-based page number.
            num_records: Page size.

        Returns:
            The page envelope, empty when the activity is not publicly shareable
            or this child is hidden.
        """
        if not activity_child_access.may_read_public_child(activity_id, db, hide_attr=self.hide_attr):
            logger.debug(
                "Refused a public activity child read; answering with an empty page",
                extra=core_logger.context(activity_id=activity_id, child=self.name),
            )
            return self._empty(page_number, num_records)
        return self._page(activity_id, db, page_number, num_records)
