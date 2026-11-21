"""The public laps route, through the production application: it follows the parent activity's visibility."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import DEFAULT_START, make_laps

_VISIBILITY = activity_constants.ActivityVisibility
_EMPTY = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/public/activities/{activity_id}/laps"


def _stage(db, activity):
    make_laps(db, activity, [{"start_time": DEFAULT_START, "total_distance": 1000.0, "avg_heart_rate": 150}])


@pytest.mark.usefixtures("public_links")
class TestPublicList:
    def test_the_laps_of_a_public_activity_need_no_credentials_and_follow_its_flags(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_hr=True)

        response = client.get(_url(activity.id))

        assert response.status_code == 200
        [lap] = response.json()["items"]
        assert (lap["total_distance"], lap["avg_heart_rate"]) == (1000.0, None)

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_answers_as_a_missing_one_does(
        self, client, make_owned_activity, visibility
    ):
        activity = make_owned_activity(visibility, stage=_stage)

        assert client.get(_url(activity.id)).json() == client.get(_url(uuid.uuid4())).json() == _EMPTY

    def test_hide_laps_and_a_hidden_activity_serve_nothing(self, client, make_owned_activity):
        no_laps = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_laps=True)
        hidden = make_owned_activity(
            _VISIBILITY.PUBLIC,
            stage=_stage,
            is_hidden=True,
            start_time=DEFAULT_START.replace(day=11),
            end_time=DEFAULT_START.replace(day=11, hour=9),
        )

        assert client.get(_url(no_laps.id)).json()["total"] == 0
        assert client.get(_url(hidden.id)).json()["total"] == 0

    def test_a_malformed_activity_id_is_a_validation_error(self, client):
        assert client.get(_url("not-a-uuid")).status_code == 422


def test_with_public_links_off_a_public_activity_serves_no_laps(client, make_owned_activity):
    activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

    assert client.get(_url(activity.id)).json() == _EMPTY
