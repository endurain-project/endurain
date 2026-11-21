"""What the laps package declares itself to be.

The paginated read itself is asserted once, in
``tests/activities/activity/test_child_collection_service.py``. What remains
package-specific is the declaration: the wrong hide flag or the wrong CRUD pair
would silently serve — or refuse — the wrong rows.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as service


class TestCollectionDeclaration:
    def test_it_is_guarded_by_the_right_parent_flag(self):
        assert service._COLLECTION.hide_attr == "hide_laps"

    def test_it_reads_through_its_own_crud(self):
        assert service._COLLECTION.fetch is activity_laps_crud.get_activity_laps
        assert service._COLLECTION.count is activity_laps_crud.count_activity_laps

    def test_it_builds_its_own_page_type(self):
        assert service._COLLECTION.build == activity_laps_schema.ActivityLapsPage.build


class TestDelegation:
    @patch("modules.activities.activity.child_collection_service.activity_child_access_service")
    def test_the_authenticated_read_goes_through_the_shared_gate(self, mock_gate):
        mock_gate.may_read_child.return_value = False
        db = MagicMock()

        page = service.list_activity_laps(5, 1, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_laps")

    @patch("modules.activities.activity.child_collection_service.activity_child_access_service")
    def test_the_public_read_goes_through_the_public_gate(self, mock_gate):
        mock_gate.may_read_public_child.return_value = False
        db = MagicMock()

        page = service.list_public_activity_laps(5, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_laps")


def _page_with_a_lap() -> activity_laps_schema.ActivityLapsPage:
    lap = activity_laps_schema.ActivityLapsRead(
        id=1,
        activity_id=5,
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        start_position_lat=45.0,
        start_position_long=6.0,
        end_position_lat=45.1,
        end_position_long=6.1,
        total_distance=1000.0,
    )
    return activity_laps_schema.ActivityLapsPage.build([lap], 1, 1, 10)


def _positions(page: activity_laps_schema.ActivityLapsPage) -> tuple:
    lap = page.items[0]
    return (lap.start_position_lat, lap.start_position_long, lap.end_position_lat, lap.end_position_long)


class TestStartEndPositions:
    @patch("modules.activities.activity_laps.service.activity_integration")
    @patch("modules.activities.activity_laps.service._COLLECTION")
    def test_a_non_owner_gets_no_positions_when_the_start_and_end_are_hidden(self, mock_collection, mock_activity):
        mock_collection.list_for_requester.return_value = _page_with_a_lap()
        mock_activity.resolve_readable_parent.return_value = MagicMock(user_id=2, hide_start_end=True)

        page = service.list_activity_laps(5, 1, MagicMock())

        assert _positions(page) == (None, None, None, None)
        assert page.items[0].total_distance == 1000.0

    @patch("modules.activities.activity_laps.service.activity_integration")
    @patch("modules.activities.activity_laps.service._COLLECTION")
    def test_the_owner_keeps_the_positions(self, mock_collection, mock_activity):
        mock_collection.list_for_requester.return_value = _page_with_a_lap()
        mock_activity.resolve_readable_parent.return_value = MagicMock(user_id=1, hide_start_end=True)

        assert _positions(service.list_activity_laps(5, 1, MagicMock())) == (45.0, 6.0, 45.1, 6.1)

    @patch("modules.activities.activity_laps.service.activity_integration")
    @patch("modules.activities.activity_laps.service._COLLECTION")
    def test_a_non_owner_keeps_the_positions_when_nothing_is_hidden(self, mock_collection, mock_activity):
        mock_collection.list_for_requester.return_value = _page_with_a_lap()
        mock_activity.resolve_readable_parent.return_value = MagicMock(user_id=2, hide_start_end=False)

        assert _positions(service.list_activity_laps(5, 1, MagicMock())) == (45.0, 6.0, 45.1, 6.1)

    @patch("modules.activities.activity_laps.service.activity_integration")
    @patch("modules.activities.activity_laps.service._COLLECTION")
    def test_a_public_viewer_gets_no_positions_when_the_start_and_end_are_hidden(self, mock_collection, mock_activity):
        mock_collection.list_public.return_value = _page_with_a_lap()
        mock_activity.resolve_public_parent.return_value = MagicMock(hide_start_end=True)

        assert _positions(service.list_public_activity_laps(5, MagicMock())) == (None, None, None, None)

    @patch("modules.activities.activity_laps.service.activity_integration")
    @patch("modules.activities.activity_laps.service._COLLECTION")
    def test_an_empty_page_skips_the_parent_lookup(self, mock_collection, mock_activity):
        mock_collection.list_public.return_value = activity_laps_schema.ActivityLapsPage.build([], 0, 1, 10)

        service.list_public_activity_laps(5, MagicMock())

        mock_activity.resolve_public_parent.assert_not_called()
