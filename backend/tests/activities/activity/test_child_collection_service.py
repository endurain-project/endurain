"""The one paginated child read, tested once.

Laps, sets and workout steps used to carry a copy of these assertions each. The
behaviour lives in ``activity/child_collection_service`` now, so it is asserted here; the
per-package tests only check that each package declares itself correctly (and laps, its
per-viewer mask).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import core.pagination as core_pagination
import modules.activities.activity.child_collection_service as child_collection_service

_RESOLVE_READABLE = (
    "modules.activities.activity.child_collection_service.activity_child_access_service.resolve_readable_parent"
)
_RESOLVE_PUBLIC = (
    "modules.activities.activity.child_collection_service.activity_child_access_service.resolve_public_parent"
)


def _parent(**kw):
    return SimpleNamespace(**{"id": 5, "user_id": 1, "hide_laps": False, **kw})


def _collection(fetch=None, count=None, mask=None):
    return child_collection_service.ChildCollection(
        name="laps",
        hide_attr="hide_laps",
        fetch=fetch or MagicMock(return_value=["row"]),
        count=count or MagicMock(return_value=1),
        build=core_pagination.Page.build,
        mask=mask,
    )


class TestListForRequester:
    @patch(_RESOLVE_READABLE)
    def test_returns_a_page_when_permitted(self, mock_resolve):
        mock_resolve.return_value = _parent()
        db = MagicMock()

        page = _collection().list_for_requester(5, 1, db, page_number=1, num_records=10)

        assert (page.items, page.total) == (["row"], 1)
        mock_resolve.assert_called_once_with(5, 1, db)

    @patch(_RESOLVE_READABLE, return_value=None)
    def test_an_invisible_parent_never_touches_persistence(self, _resolve):
        """A refused read must not query, so it cannot leak timing or rows."""
        fetch, count = MagicMock(), MagicMock()

        page = _collection(fetch, count).list_for_requester(5, 1, MagicMock(), page_number=1, num_records=10)

        assert (page.items, page.total) == ([], 0)
        fetch.assert_not_called()
        count.assert_not_called()

    @patch(_RESOLVE_READABLE)
    def test_the_hide_flag_refuses_a_non_owner_without_querying(self, mock_resolve):
        mock_resolve.return_value = _parent(hide_laps=True)
        fetch, count = MagicMock(), MagicMock()

        page = _collection(fetch, count).list_for_requester(5, 2, MagicMock(), page_number=1, num_records=10)

        assert (page.items, page.total) == ([], 0)
        fetch.assert_not_called()
        count.assert_not_called()

    @patch(_RESOLVE_READABLE)
    def test_paging_is_forwarded_and_the_total_spans_every_page(self, mock_resolve):
        """``total`` must count all matching rows, not the slice returned."""
        mock_resolve.return_value = _parent()
        fetch = MagicMock(return_value=["row"])
        db = MagicMock()

        page = _collection(fetch, MagicMock(return_value=250)).list_for_requester(
            5, 1, db, page_number=2, num_records=100
        )

        fetch.assert_called_once_with(5, db, page_number=2, num_records=100)
        assert page.total == 250
        assert page.next == 3


class TestListPublic:
    @patch(_RESOLVE_PUBLIC)
    def test_returns_a_page_when_public(self, mock_resolve):
        mock_resolve.return_value = _parent()
        db = MagicMock()

        page = _collection().list_public(5, db, page_number=1, num_records=10)

        assert page.items == ["row"]
        mock_resolve.assert_called_once_with(5, db)

    @patch(_RESOLVE_PUBLIC, return_value=None)
    def test_a_non_public_parent_never_touches_persistence(self, _resolve):
        fetch, count = MagicMock(), MagicMock()

        page = _collection(fetch, count).list_public(5, MagicMock(), page_number=1, num_records=10)

        assert (page.items, page.total) == ([], 0)
        fetch.assert_not_called()
        count.assert_not_called()

    @patch(_RESOLVE_PUBLIC)
    def test_the_hide_flag_refuses_an_anonymous_viewer(self, mock_resolve):
        mock_resolve.return_value = _parent(hide_laps=True)
        fetch = MagicMock()

        page = _collection(fetch).list_public(5, MagicMock(), page_number=1, num_records=10)

        assert page.items == []
        fetch.assert_not_called()

    @patch(_RESOLVE_READABLE)
    @patch(_RESOLVE_PUBLIC, return_value=None)
    def test_the_public_gate_is_a_different_question(self, _public, mock_readable):
        """An anonymous read must never fall through to the authenticated gate."""
        _collection().list_public(5, MagicMock(), page_number=1, num_records=10)

        mock_readable.assert_not_called()


class TestViewerMask:
    """A package's per-viewer mask runs for everyone but the owner."""

    @patch(_RESOLVE_READABLE)
    def test_a_non_owner_gets_the_masked_rows(self, mock_resolve):
        parent = _parent()
        mock_resolve.return_value = parent
        mask = MagicMock(return_value=["masked"])

        page = _collection(mask=mask).list_for_requester(5, 2, MagicMock(), page_number=1, num_records=10)

        assert page.items == ["masked"]
        mask.assert_called_once_with(["row"], parent)

    @patch(_RESOLVE_PUBLIC)
    def test_an_anonymous_viewer_gets_the_masked_rows(self, mock_resolve):
        mock_resolve.return_value = _parent()
        mask = MagicMock(return_value=["masked"])

        page = _collection(mask=mask).list_public(5, MagicMock(), page_number=1, num_records=10)

        assert page.items == ["masked"]

    @patch(_RESOLVE_READABLE)
    def test_the_owner_gets_the_rows_unmasked(self, mock_resolve):
        mock_resolve.return_value = _parent()
        mask = MagicMock()

        page = _collection(mask=mask).list_for_requester(5, 1, MagicMock(), page_number=1, num_records=10)

        assert page.items == ["row"]
        mask.assert_not_called()

    def test_a_resolved_parent_is_masked_for_a_non_owner(self):
        mask = MagicMock(return_value=["masked"])

        page = _collection(mask=mask).list_for_activity(_parent(), 2, MagicMock(), page_number=1, num_records=10)

        assert page.items == ["masked"]


class TestListForActivity:
    """A child read for an activity the caller already resolved, so no second lookup runs."""

    def test_returns_a_page_for_a_viewer_the_flag_does_not_hide_from(self):
        db = MagicMock()
        fetch = MagicMock(return_value=["row"])

        page = _collection(fetch).list_for_activity(_parent(), 2, db, page_number=1, num_records=10)

        assert (page.items, page.total) == (["row"], 1)
        fetch.assert_called_once_with(5, db, page_number=1, num_records=10)

    def test_a_non_owner_is_answered_with_an_empty_page_and_nothing_is_queried(self):
        fetch, count = MagicMock(), MagicMock()

        page = _collection(fetch, count).list_for_activity(
            _parent(hide_laps=True), 2, MagicMock(), page_number=1, num_records=10
        )

        assert (page.items, page.total) == ([], 0)
        fetch.assert_not_called()
        count.assert_not_called()

    def test_the_owner_reads_despite_the_flag(self):
        page = _collection().list_for_activity(_parent(hide_laps=True), 1, MagicMock(), page_number=1, num_records=10)

        assert page.items == ["row"]

    def test_an_anonymous_viewer_is_hidden_from_by_the_flag(self):
        fetch = MagicMock()

        page = _collection(fetch).list_for_activity(
            _parent(hide_laps=True), None, MagicMock(), page_number=1, num_records=10
        )

        assert page.items == []
        fetch.assert_not_called()
