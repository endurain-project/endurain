"""What the laps package declares itself to be.

The paginated read itself is asserted once, in
``tests/activities/activity/test_child_collection.py``. What remains
package-specific is the declaration: the wrong hide flag or the wrong CRUD pair
would silently serve — or refuse — the wrong rows.
"""

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
    @patch("modules.activities.activity.child_collection.activity_child_access")
    def test_the_authenticated_read_goes_through_the_shared_gate(self, mock_gate):
        mock_gate.may_read_child.return_value = False
        db = MagicMock()

        page = service.list_activity_laps(5, 1, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.may_read_child.assert_called_once_with(5, 1, db, hide_attr="hide_laps")

    @patch("modules.activities.activity.child_collection.activity_child_access")
    def test_the_public_read_goes_through_the_public_gate(self, mock_gate):
        mock_gate.may_read_public_child.return_value = False
        db = MagicMock()

        page = service.list_public_activity_laps(5, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.may_read_public_child.assert_called_once_with(5, db, hide_attr="hide_laps")
