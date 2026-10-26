"""The combined activity detail is the activity plus its child collections, gated once."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_detail.service as detail_service

_ACTIVITY = "modules.activities.activity_detail.service.activity_integration"
_LAPS = "modules.activities.activity_detail.service.activity_laps_integration"
_SETS = "modules.activities.activity_detail.service.activity_sets_integration"
_STEPS = "modules.activities.activity_detail.service.activity_workout_steps_integration"


@pytest.fixture
def children():
    with patch(_LAPS) as laps, patch(_SETS) as sets, patch(_STEPS) as steps:
        laps.list_for_activity.return_value = "laps-page"
        sets.list_for_activity.return_value = "sets-page"
        steps.list_for_activity.return_value = "steps-page"
        yield laps, sets, steps


def _detail():
    """Replace the response model, so stand-in pages need not validate."""
    return patch.object(detail_service.activity_detail_schema, "ActivityDetailRead")


class TestGetActivityDetail:
    def test_reads_the_activity_once_and_each_child_for_it(self, children):
        laps, sets, steps = children
        activity, db = SimpleNamespace(id=5, user_id=3), MagicMock()
        with patch(_ACTIVITY) as activity_integration, _detail() as build:
            activity_integration.get_readable_activity.return_value = activity
            detail_service.get_activity_detail(5, 1, db)

        activity_integration.get_readable_activity.assert_called_once_with(5, 1, db)
        laps.list_for_activity.assert_called_once_with(activity, 1, db)
        sets.list_for_activity.assert_called_once_with(activity, 1, db)
        steps.list_for_activity.assert_called_once_with(activity, 1, db)
        build.assert_called_once_with(activity=activity, laps="laps-page", sets="sets-page", workout_steps="steps-page")

    def test_an_activity_the_caller_cannot_see_is_not_found_and_no_child_is_read(self, children):
        with patch(_ACTIVITY) as activity_integration:
            activity_integration.get_readable_activity.side_effect = core_exceptions.NotFoundError("nope")
            with pytest.raises(core_exceptions.NotFoundError):
                detail_service.get_activity_detail(5, 1, MagicMock())

        for child in children:
            child.list_for_activity.assert_not_called()


class TestGetPublicActivityDetail:
    def test_reads_the_public_activity_and_each_child_as_anonymous(self, children):
        laps, sets, steps = children
        activity, db = SimpleNamespace(id=5, user_id=3), MagicMock()
        with patch(_ACTIVITY) as activity_integration, _detail():
            activity_integration.get_public_activity.return_value = activity
            detail_service.get_public_activity_detail(5, db)

        activity_integration.get_public_activity.assert_called_once_with(5, db)
        laps.list_for_activity.assert_called_once_with(activity, None, db)
        sets.list_for_activity.assert_called_once_with(activity, None, db)
        steps.list_for_activity.assert_called_once_with(activity, None, db)

    def test_an_activity_that_is_not_public_is_not_found(self, children):
        with patch(_ACTIVITY) as activity_integration:
            activity_integration.get_public_activity.side_effect = core_exceptions.NotFoundError("nope")
            with pytest.raises(core_exceptions.NotFoundError):
                detail_service.get_public_activity_detail(5, MagicMock())
