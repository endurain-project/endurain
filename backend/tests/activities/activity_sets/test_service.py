"""What the workout sets package declares itself to be.

The paginated read itself is asserted once, in
``tests/activities/activity/test_child_collection_service.py``. What remains
package-specific is the declaration: the wrong hide flag or the wrong CRUD pair
would silently serve — or refuse — the wrong rows.
"""

from unittest.mock import MagicMock, patch

import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as service


class TestCollectionDeclaration:
    def test_it_is_guarded_by_the_right_parent_flag(self):
        assert service._COLLECTION.hide_attr == "hide_workout_sets_steps"

    def test_it_reads_through_its_own_crud(self):
        assert service._COLLECTION.fetch is activity_sets_crud.get_activity_sets
        assert service._COLLECTION.count is activity_sets_crud.count_activity_sets

    def test_it_builds_its_own_page_type(self):
        assert service._COLLECTION.build == activity_sets_schema.ActivitySetsPage.build


class TestDelegation:
    @patch("modules.activities.activity.child_collection_service.activity_child_access_service")
    def test_the_authenticated_read_goes_through_the_shared_gate(self, mock_gate):
        mock_gate.resolve_readable_parent.return_value = None
        db = MagicMock()

        page = service.list_activity_sets(5, 1, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.resolve_readable_parent.assert_called_once_with(5, 1, db)

    @patch("modules.activities.activity.child_collection_service.activity_child_access_service")
    def test_the_public_read_goes_through_the_public_gate(self, mock_gate):
        mock_gate.resolve_public_parent.return_value = None
        db = MagicMock()

        page = service.list_public_activity_sets(5, db)

        assert (page.items, page.total) == ([], 0)
        mock_gate.resolve_public_parent.assert_called_once_with(5, db)
