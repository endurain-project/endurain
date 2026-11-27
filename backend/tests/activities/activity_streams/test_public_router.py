"""The public streams route, through the production application: it follows the parent activity's visibility."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_samples

_VISIBILITY = activity_constants.ActivityVisibility


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/public/activities/{activity_id}/streams"


def _stage(db, activity):
    make_samples(
        db,
        activity,
        [0, 1000, 2000],
        heart_rate=[100.0, 190.0, 190.0],
        power=[250.5, 260.0, 270.0],
        latitude=[38.0, 38.1, 38.2],
        longitude=[-9.0, -9.1, -9.2],
    )


@pytest.mark.usefixtures("public_links")
class TestPublic:
    def test_a_public_activity_needs_no_credentials_and_follows_its_flags(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_hr=True, hide_map=True)

        response = client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert body["offsets_ms"] == [0, 1000, 2000]
        assert body["power"] == [250.5, 260.0, 270.0]
        assert (body["heart_rate"], body["heart_rate_zones"], body["latitude"], body["longitude"]) == (
            None,
            None,
            None,
            None,
        )

    def test_the_hr_zones_survive_a_hidden_start_time(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage, hide_start_time=True)

        body = client.get(_url(activity.id)).json()

        assert body["offsets_ms"] == [0, 1000, 2000]
        assert body["heart_rate_zones"]["zone_5"]["time_seconds"] == 1

    def test_max_points_averages_the_samples_and_is_validated(self, client, make_owned_activity):
        activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

        assert client.get(_url(activity.id), params={"max_points": 2}).json()["offsets_ms"] == [0, 1500]
        assert client.get(_url(activity.id), params={"max_points": 1}).status_code == 422

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_answers_as_a_missing_one_does(
        self, client, make_owned_activity, visibility
    ):
        activity = make_owned_activity(visibility, stage=_stage)

        refused = client.get(_url(activity.id))
        missing = client.get(_url(uuid.uuid4()))

        assert refused.status_code == missing.status_code == 404
        assert refused.json()["type"] == "urn:endurain:error:not-found"
        assert refused.json()["detail"] == missing.json()["detail"]


def test_with_public_links_off_a_public_activity_serves_no_streams(client, make_owned_activity):
    activity = make_owned_activity(_VISIBILITY.PUBLIC, stage=_stage)

    assert client.get(_url(activity.id)).status_code == 404
