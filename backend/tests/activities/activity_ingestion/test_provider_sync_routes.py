"""The providers' own "retrieve activities" routes queue a job instead of working in the API."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.garmin.provider_registry as garmin_provider_registry
import modules.garmin.router as garmin_router
import modules.strava.provider_registry as strava_provider_registry
import modules.strava.router as strava_router

_CASES = [
    pytest.param(
        garmin_router.garminconnect_retrieve_activities_days,
        garmin_router,
        garmin_provider_registry.PROVIDER_NAME,
        id="garmin",
    ),
    pytest.param(
        strava_router.strava_retrieve_activities_days,
        strava_router,
        strava_provider_registry.PROVIDER_NAME,
        id="strava",
    ),
]


def _call(route, **overrides):
    kwargs = {
        "request": MagicMock(),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 8),
        "token_user_id": 7,
        "db": MagicMock(),
        "storage": "storage",
    }
    if route is strava_router.strava_retrieve_activities_days:
        kwargs.update(_validate_access_token=None, _check_scopes=None)
    kwargs.update(overrides)
    return route(**kwargs)


@pytest.mark.parametrize(("route", "module", "provider"), _CASES)
class TestRetrieveActivitiesRoutes:
    def test_queues_a_job_for_that_provider_and_returns_its_handle(self, route, module, provider):
        job = MagicMock()
        with patch.object(module.activity_ingestion_integration, "request_provider_sync", return_value=job) as request:
            result = _call(route)

        assert result is job
        user_id, name, window_start, window_end, storage, _db = request.call_args.args
        assert (user_id, name, storage) == (7, provider, "storage")
        # The whole of both end days, in UTC.
        assert window_start == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        assert window_end.date() == date(2026, 1, 8) and window_end.hour == 23

    def test_a_reversed_range_is_rejected_before_anything_is_queued(self, route, module, provider):
        with (
            patch.object(module.activity_ingestion_integration, "request_provider_sync") as request,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            _call(route, start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))

        request.assert_not_called()

    def test_the_work_is_not_scheduled_on_the_api_process(self, route, module, provider):
        """The old routes used BackgroundTasks, which ran a long range on an API worker thread."""
        import inspect

        assert "background_tasks" not in inspect.signature(route).parameters
        assert not inspect.iscoroutinefunction(route)
