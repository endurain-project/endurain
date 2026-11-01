"""What the workout sets package declares itself to be.

The paginated read itself is asserted once, in
``tests/activities/activity/test_child_collection_service.py``. What remains
package-specific is the declaration: the wrong hide flag or the wrong CRUD pair
would silently serve — or refuse — the wrong rows — and the fields each flag clears, which
keeps a set from serving the start its activity hides.
"""

import dataclasses
from datetime import UTC, datetime
from types import SimpleNamespace
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


def _set() -> activity_sets_schema.ActivitySetsRead:
    return activity_sets_schema.ActivitySetsRead(
        id=1,
        activity_id=5,
        duration=30.0,
        repetitions=10,
        weight=50.0,
        set_type="active",
        start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
        category=1,
        category_subtype=2,
    )


def _parent(**flags) -> SimpleNamespace:
    return SimpleNamespace(
        **{"id": 5, "user_id": 1, "hide_workout_sets_steps": False, "hide_start_time": False} | flags
    )


def _reading(*sets):
    """The sets collection as declared, reading the given rows instead of the database."""
    return dataclasses.replace(
        service._COLLECTION, fetch=MagicMock(return_value=list(sets)), count=MagicMock(return_value=len(sets))
    )


class TestViewerMask:
    """A set carries its own start instant, so ``hide_start_time`` withholds it like the activity's."""

    def test_it_declares_the_field_map(self):
        assert service._COLLECTION.fields_by_hide_flag == {"hide_start_time": ("start_time",)}

    def test_a_non_owner_does_not_read_a_hidden_start(self):
        with patch.object(service, "_COLLECTION", _reading(_set())):
            page = service.list_for_activity(_parent(hide_start_time=True), 2, MagicMock())

        assert page.items[0].start_time is None
        untouched = set(activity_sets_schema.ActivitySetsRead.model_fields) - {"start_time"}
        assert all(getattr(page.items[0], field) == getattr(_set(), field) for field in untouched)

    def test_the_masked_page_is_a_valid_response(self):
        with patch.object(service, "_COLLECTION", _reading(_set())):
            page = service.list_for_activity(_parent(hide_start_time=True), 2, MagicMock())

        assert activity_sets_schema.ActivitySetsPage.model_validate(page.model_dump()).items[0].start_time is None

    def test_a_non_owner_reads_the_start_when_it_is_shown(self):
        with patch.object(service, "_COLLECTION", _reading(_set())):
            page = service.list_for_activity(_parent(), 2, MagicMock())

        assert page.items == [_set()]

    def test_the_owner_reads_a_hidden_start(self):
        with patch.object(service, "_COLLECTION", _reading(_set())):
            page = service.list_for_activity(_parent(hide_start_time=True), 1, MagicMock())

        assert page.items == [_set()]
