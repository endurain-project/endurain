"""The providers' own "retrieve activities" routes queue a job instead of working in the API."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.garmin.constants as garmin_constants
import modules.garmin.router as garmin_router
import modules.garmin.sync_service as garmin_sync_service
import modules.strava.constants as strava_constants
import modules.strava.router as strava_router
import modules.strava.sync_service as strava_sync_service

_CASES = [
    pytest.param(
        garmin_router.garminconnect_retrieve_activities_days,
        garmin_sync_service,
        garmin_constants.PROVIDER_NAME,
        id="garmin",
    ),
    pytest.param(
        strava_router.strava_retrieve_activities_days,
        strava_sync_service,
        strava_constants.PROVIDER_NAME,
        id="strava",
    ),
]


@pytest.fixture(autouse=True)
def users_today():
    with patch.object(garmin_sync_service.users_integration, "local_today", return_value=date(2026, 1, 31)):
        yield


def _call(route, **overrides):
    kwargs = {
        "request": MagicMock(),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 8),
        "token_user_id": 7,
        "db": MagicMock(),
        "storage": "storage",
    }
    kwargs.update(overrides)
    return route(**kwargs)


@pytest.mark.parametrize(("route", "module", "provider"), _CASES)
class TestRetrieveActivitiesRoutes:
    def test_queues_a_job_for_that_provider_and_returns_its_handle(self, route, module, provider):
        job = MagicMock()
        with patch.object(
            module.activity_ingestion_integration.activity_ingestion_service, "accept_refresh", return_value=job
        ) as request:
            result = _call(route)

        assert result is job
        user_id, storage, _db = request.call_args.args
        name, window_start, window_end = (
            request.call_args.kwargs[k] for k in ("provider", "window_start", "window_end")
        )
        assert (user_id, name, storage) == (7, provider, "storage")
        # The whole of both end days, in UTC.
        assert window_start == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        assert window_end.date() == date(2026, 1, 8) and window_end.hour == 23

    def test_a_reversed_range_is_rejected_before_anything_is_queued(self, route, module, provider):
        with (
            patch.object(module.activity_ingestion_integration.activity_ingestion_service, "accept_refresh") as request,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            _call(route, start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))

        request.assert_not_called()

    def test_the_work_is_not_scheduled_on_the_api_process(self, route, module, provider):
        """The old routes used BackgroundTasks, which ran a long range on an API worker thread."""
        import inspect

        assert "background_tasks" not in inspect.signature(route).parameters
        assert not inspect.iscoroutinefunction(route)
