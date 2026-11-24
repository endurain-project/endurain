"""The public stream routes, through the production application: they follow the parent activity's visibility."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_streams.constants as stream_constants
from tests._factories.activities import make_stream

_VISIBILITY = activity_constants.ActivityVisibility
_HR = stream_constants.STREAM_TYPE_HR
_POWER = stream_constants.STREAM_TYPE_POWER
_TIME = "2025-03-10T08:00:00"
_EMPTY = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}


def _url(activity_id: uuid.UUID | str, stream_type: str = "") -> str:
    base = f"{core_config.ROOT_PATH}/public/activities/{activity_id}/streams"
    return base + (f"/{stream_type}" if stream_type else "")


def _stage(db, activity):
    make_stream(db, activity, _HR, [{"time": _TIME, "hr": 100}, {"time": _TIME, "hr": 190}])
    make_stream(db, activity, _POWER, [{"time": _TIME, "power": 250.5}])


@pytest.mark.usefixtures("public_links")
class TestPublic:
    def test_the_streams_of_a_public_activity_need_no_credentials_and_follow_its_flags(
        self, client, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_hr=True, hide_start_time=True)

        response = client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert [item["stream_type"] for item in body["items"]] == ["power"]
        assert body["items"][0]["stream_waypoints"] == [{"power": 250.5}]

    def test_one_stream_of_a_public_activity_is_served_with_its_hr_zones(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, total_timer_time=100.0)

        response = client.get(_url(activity.id, "heart_rate"))

        assert response.status_code == 200
        assert response.json()["zone_percentages"]["hr"]["zone_5"]["percent"] == 50.0

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_answers_as_a_missing_one_does(
        self, client, make_owned_activity, visibility
    ):
        activity = make_owned_activity(visibility, stage=_stage)

        assert client.get(_url(activity.id)).json() == client.get(_url(uuid.uuid4())).json() == _EMPTY
        assert client.get(_url(activity.id, "power")).status_code == 404

    def test_a_hidden_stream_is_a_404(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_power=True)

        response = client.get(_url(activity.id, "power"))

        assert response.status_code == 404
        assert response.json()["type"] == "urn:endurain:error:not-found"

    def test_a_type_that_is_not_a_stream_type_is_a_validation_error(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

        assert client.get(_url(activity.id, "altitude")).status_code == 422


def test_with_public_links_off_a_public_activity_serves_no_streams(client, make_owned_activity):
    activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

    assert client.get(_url(activity.id)).json() == _EMPTY
    assert client.get(_url(activity.id, "power")).status_code == 404
