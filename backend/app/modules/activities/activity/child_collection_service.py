"""One paginated read of an activity's child collection, defined once.

Laps, sets and workout steps are the same read three times over: resolve the parent through
the shared :mod:`~modules.activities.activity.child_access_service` gate, apply the child's
hide flag, page the rows, count them, mask them for a non-owner, and wrap the two in the page
envelope — with "refused" and "there are none" deliberately answering the same way, so the
endpoint cannot be used to probe which activities exist.

A divergence between copies would be in the part that decides what a non-owner
may see, so a child package declares only *what* it is — its hide flag, its two
CRUD calls, its page type and, when its rows repeat data the parent hides field by
field, its mask — and this owns *how* the read runs.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.child_access_service as activity_child_access_service
import modules.activities.activity.schema as activity_schema

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
        fields_by_hide_flag: The row fields each of the parent's other ``hide_*`` flags
            withholds from a non-owner, cleared when the flag is set; empty when the rows
            carry nothing those flags cover.
    """

    name: str
    hide_attr: str
    fetch: Callable[..., list[Any]]
    count: Callable[[int, Session], int]
    build: Callable[[list[Any], int, int, int], PageT]
    fields_by_hide_flag: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def _empty(self, page_number: int, num_records: int) -> PageT:
        """Return the empty page — the answer to both "none" and "not allowed".

        Args:
            page_number: 1-based page number.
            num_records: Page size.

        Returns:
            The empty page.
        """
        return self.build([], 0, page_number, num_records)

    def _mask(self, items: list[Any], activity: activity_schema.ActivityRead) -> list[Any]:
        """Clear what the parent's ``hide_*`` flags withhold from a viewer who is not the owner.

        Args:
            items: The rows about to be served.
            activity: The parent activity, carrying its ``hide_*`` flags.

        Returns:
            The rows, with every field a set flag covers cleared.
        """
        hidden = [
            column
            for flag, columns in self.fields_by_hide_flag.items()
            if getattr(activity, flag)
            for column in columns
        ]
        if not hidden:
            return items
        return [item.model_copy(update=dict.fromkeys(hidden)) for item in items]

    def _page(
        self,
        activity: activity_schema.ActivityRead,
        requester_user_id: int | None,
        page_number: int,
        num_records: int,
        db: Session,
    ) -> PageT:
        """Read one page and its total, masked for a viewer who is not the owner.

        Args:
            activity: The parent activity, as the viewer is allowed to see it.
            requester_user_id: The authenticated viewer, or ``None`` for an anonymous one.
            page_number: 1-based page number.
            num_records: Page size.
            db: Database session.

        Returns:
            The page and its total.
        """
        items = self.fetch(activity.id, db, page_number=page_number, num_records=num_records)
        if requester_user_id != activity.user_id:
            items = self._mask(items, activity)
        return self.build(items, self.count(activity.id, db), page_number, num_records)

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
        activity = activity_child_access_service.resolve_readable_parent(activity_id, requester_user_id, db)
        if activity is None:
            logger.debug(
                "Refused an activity child read; answering with an empty page",
                extra=core_logger.context(
                    activity_id=activity_id,
                    requester_user_id=requester_user_id,
                    child=self.name,
                ),
            )
            return self._empty(page_number, num_records)
        return self.list_for_activity(activity, requester_user_id, db, page_number=page_number, num_records=num_records)

    def list_for_activity(
        self,
        activity: activity_schema.ActivityRead,
        requester_user_id: int | None,
        db: Session,
        *,
        page_number: int,
        num_records: int,
    ) -> PageT:
        """Return one page for an activity the caller has already resolved.

        The caller has already established that the viewer may see ``activity`` (as
        the viewer sees it, so its ``hide_*`` flags are present), so this only
        applies the child's own flag and field masking and runs no lookup of the parent.

        Args:
            activity: The parent activity, as the viewer is allowed to see it.
            requester_user_id: The authenticated viewer, or ``None`` for an anonymous one.
            db: Database session.
            page_number: 1-based page number.
            num_records: Page size.

        Returns:
            The page envelope, empty when the child is hidden from this viewer.
        """
        if activity_child_access_service.is_hidden_from(activity, requester_user_id, hide_attr=self.hide_attr):
            logger.debug(
                "Withheld an activity child; answering with an empty page",
                extra=core_logger.context(activity_id=activity.id, child=self.name),
            )
            return self._empty(page_number, num_records)
        return self._page(activity, requester_user_id, page_number, num_records, db)

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
        activity = activity_child_access_service.resolve_public_parent(activity_id, db)
        if activity is None:
            logger.debug(
                "Refused a public activity child read; answering with an empty page",
                extra=core_logger.context(activity_id=activity_id, child=self.name),
            )
            return self._empty(page_number, num_records)
        return self.list_for_activity(activity, None, db, page_number=page_number, num_records=num_records)
