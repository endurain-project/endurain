"""Each child package reads its rows for an activity the caller already holds."""

from unittest.mock import MagicMock, patch

import pytest

import core.pagination as core_pagination
import modules.activities.activity_laps.integration_service as laps_integration
import modules.activities.activity_laps.service as laps_service
import modules.activities.activity_sets.integration_service as sets_integration
import modules.activities.activity_sets.service as sets_service
import modules.activities.activity_workout_steps.integration_service as steps_integration
import modules.activities.activity_workout_steps.service as steps_service

CHILDREN = [
    pytest.param(laps_service, laps_integration, id="laps"),
    pytest.param(sets_service, sets_integration, id="sets"),
    pytest.param(steps_service, steps_integration, id="workout-steps"),
]


@pytest.mark.parametrize(("service", "integration"), CHILDREN)
class TestListForActivity:
    def test_the_service_reads_the_first_page_through_its_collection(self, service, integration):
        activity, db = MagicMock(), MagicMock()
        with patch.object(service, "_COLLECTION") as collection:
            result = service.list_for_activity(activity, 7, db)

        collection.list_for_activity.assert_called_once_with(
            activity, 7, db, page_number=1, num_records=core_pagination.DEFAULT_CHILD_NUM_RECORDS
        )
        assert result is collection.list_for_activity.return_value

    def test_the_surface_delegates_to_the_service(self, service, integration):
        activity, db = MagicMock(), MagicMock()
        with patch.object(integration.__dict__[_service_alias(integration)], "list_for_activity") as read:
            result = integration.list_for_activity(activity, None, db)

        read.assert_called_once_with(activity, None, db)
        assert result is read.return_value


def _service_alias(integration) -> str:
    """Name the service module an integration surface imports, whatever alias it gave it."""
    return next(name for name, value in vars(integration).items() if name.endswith("_service"))
