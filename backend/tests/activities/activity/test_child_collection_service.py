"""The one paginated child read, tested once.

Laps, sets and workout steps used to carry a copy of these assertions each. The
behaviour lives in ``activity/child_collection_service`` now, so it is asserted here; the
per-package tests only check that each package declares itself correctly (and laps, its
declared field masking).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

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


def _collection(fetch=None, count=None, fields_by_hide_flag=None):
    return child_collection_service.ChildCollection(
        name="laps",
        hide_attr="hide_laps",
        fetch=fetch or MagicMock(return_value=["row"]),
        count=count or MagicMock(return_value=1),
        build=core_pagination.Page.build,
        **({} if fields_by_hide_flag is None else {"fields_by_hide_flag": fields_by_hide_flag}),
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


_FIELDS = {"hide_map": ("lat", "long"), "hide_hr": ("heart_rate",)}


class _Row(BaseModel):
    lat: float | None = 1.0
    long: float | None = 2.0
    heart_rate: int | None = 60
    distance: float = 10.0


class TestViewerMask:
    """A package's declared flag-to-field map clears fields for everyone but the owner."""

    @patch(_RESOLVE_READABLE)
    def test_a_non_owner_gets_the_covered_fields_cleared(self, mock_resolve):
        mock_resolve.return_value = _parent(hide_map=True, hide_hr=False)
        fetch = MagicMock(return_value=[_Row()])

        page = _collection(fetch, fields_by_hide_flag=_FIELDS).list_for_requester(
            5, 2, MagicMock(), page_number=1, num_records=10
        )

        assert page.items == [_Row(lat=None, long=None)]

    @patch(_RESOLVE_READABLE)
    def test_a_flag_that_is_unset_clears_nothing(self, mock_resolve):
        mock_resolve.return_value = _parent(hide_map=False, hide_hr=False)
        fetch = MagicMock(return_value=[_Row()])

        page = _collection(fetch, fields_by_hide_flag=_FIELDS).list_for_requester(
            5, 2, MagicMock(), page_number=1, num_records=10
        )

        assert page.items == [_Row()]

    @patch(_RESOLVE_PUBLIC)
    def test_an_anonymous_viewer_gets_the_covered_fields_cleared(self, mock_resolve):
        mock_resolve.return_value = _parent(hide_map=False, hide_hr=True)
        fetch = MagicMock(return_value=[_Row()])

        page = _collection(fetch, fields_by_hide_flag=_FIELDS).list_public(
            5, MagicMock(), page_number=1, num_records=10
        )

        assert page.items == [_Row(heart_rate=None)]

    @patch(_RESOLVE_READABLE)
    def test_the_owner_gets_the_rows_unmasked(self, mock_resolve):
        mock_resolve.return_value = _parent(hide_map=True, hide_hr=True)
        fetch = MagicMock(return_value=[_Row()])

        page = _collection(fetch, fields_by_hide_flag=_FIELDS).list_for_requester(
            5, 1, MagicMock(), page_number=1, num_records=10
        )

        assert page.items == [_Row()]

    def test_a_resolved_parent_is_masked_for_a_non_owner(self):
        fetch = MagicMock(return_value=[_Row()])

        page = _collection(fetch, fields_by_hide_flag=_FIELDS).list_for_activity(
            _parent(hide_map=True, hide_hr=True), 2, MagicMock(), page_number=1, num_records=10
        )

        assert page.items == [_Row(lat=None, long=None, heart_rate=None)]

    def test_a_collection_declaring_no_fields_serves_the_rows_as_they_are(self):
        page = _collection().list_for_activity(_parent(), 2, MagicMock(), page_number=1, num_records=10)

        assert page.items == ["row"]


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
