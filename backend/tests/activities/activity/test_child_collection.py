"""The one paginated child read, tested once.

Laps, sets and workout steps used to carry a copy of these assertions each. The
behaviour lives in ``activity/child_collection`` now, so it is asserted here; the
per-package tests only check that each package declares itself correctly.
"""

from unittest.mock import MagicMock, patch

import core.pagination as core_pagination
import modules.activities.activity.child_collection as child_collection

_GATE = "modules.activities.activity.child_collection.activity_child_access"


def _collection(fetch=None, count=None):
    return child_collection.ChildCollection(
        name="laps",
        hide_attr="hide_laps",
        fetch=fetch or MagicMock(return_value=["row"]),
        count=count or MagicMock(return_value=1),
        build=core_pagination.Page.build,
    )


class TestListForRequester:
    @patch(_GATE)
    def test_returns_a_page_when_permitted(self, mock_gate):
        mock_gate.may_read_child.return_value = True
        db = MagicMock()

        page = _collection().list_for_requester(5, 1, db, page_number=1, num_records=10)

        assert (page.items, page.total) == (["row"], 1)
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_laps")

    @patch(_GATE)
    def test_denied_never_touches_persistence(self, mock_gate):
        """A refused read must not query, so it cannot leak timing or rows."""
        mock_gate.may_read_child.return_value = False
        fetch, count = MagicMock(), MagicMock()

        page = _collection(fetch, count).list_for_requester(5, 1, MagicMock(), page_number=1, num_records=10)

        assert (page.items, page.total) == ([], 0)
        fetch.assert_not_called()
        count.assert_not_called()

    @patch(_GATE)
    def test_paging_is_forwarded_and_the_total_spans_every_page(self, mock_gate):
        """``total`` must count all matching rows, not the slice returned."""
        mock_gate.may_read_child.return_value = True
        fetch = MagicMock(return_value=["row"])
        db = MagicMock()

        page = _collection(fetch, MagicMock(return_value=250)).list_for_requester(
            5, 1, db, page_number=2, num_records=100
        )

        fetch.assert_called_once_with(5, db, page_number=2, num_records=100)
        assert page.total == 250
        assert page.next == 3


class TestListPublic:
    @patch(_GATE)
    def test_returns_a_page_when_public(self, mock_gate):
        mock_gate.may_read_public_child.return_value = True
        db = MagicMock()

        page = _collection().list_public(5, db, page_number=1, num_records=10)

        assert page.items == ["row"]
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_laps")

    @patch(_GATE)
    def test_denied_never_touches_persistence(self, mock_gate):
        mock_gate.may_read_public_child.return_value = False
        fetch, count = MagicMock(), MagicMock()

        page = _collection(fetch, count).list_public(5, MagicMock(), page_number=1, num_records=10)

        assert (page.items, page.total) == ([], 0)
        fetch.assert_not_called()
        count.assert_not_called()

    @patch(_GATE)
    def test_the_public_gate_is_a_different_question(self, mock_gate):
        """An anonymous read must never fall through to the authenticated gate."""
        mock_gate.may_read_public_child.return_value = False

        _collection().list_public(5, MagicMock(), page_number=1, num_records=10)

        mock_gate.may_read_child.assert_not_called()
