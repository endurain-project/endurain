"""The streams route, through the production application: what a viewer reads of one activity."""

import uuid

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_samples

_VISIBILITY = activity_constants.ActivityVisibility
_CHANNELS = ("latitude", "longitude", "elevation", "heart_rate", "power", "cadence", "speed", "pace", "temperature")


def _url(activity_id: uuid.UUID | str) -> str:
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/streams"


def _stage(db, activity):
    make_samples(
        db,
        activity,
        [0, 1000, 2000],
        heart_rate=[100.0, 190.0, 190.0],
        power=[250.5, 260.0, 270.0],
        speed=[4.0, 0.0, 2.0],
    )


class TestRead:
    def test_the_owner_gets_one_object_with_the_timeline_the_channels_and_the_hr_zones(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(stage=_stage, total_timer_time=100.0)

        response = sign_in(people.owner).client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"offsets_ms", "heart_rate_zones", *_CHANNELS}
        assert body["offsets_ms"] == [0, 1000, 2000]
        assert body["heart_rate"] == [100.0, 190.0, 190.0]
        assert body["power"] == [250.5, 260.0, 270.0]
        assert body["speed"] == [4.0, 0.0, 2.0]
        assert body["pace"] == [0.25, None, 0.5]
        assert [body[name] for name in ("latitude", "longitude", "elevation", "cadence", "temperature")] == [None] * 5
        assert body["heart_rate_zones"]["zone_5"] == {"percent": 50.0, "hr": ">= 180", "time_seconds": 1}

    def test_a_value_is_served_as_recorded_not_with_the_noise_of_its_single_precision_storage(
        self, sign_in, people, make_owned_activity
    ):
        def stage(db, activity):
            make_samples(db, activity, [0, 1000], elevation=[12.3, 12.4], speed=[3.2, 2.7], temperature=[21.6, 21.7])

        activity = make_owned_activity(stage=stage)

        body = sign_in(people.owner).client.get(_url(activity.id)).json()

        assert body["elevation"] == [12.3, 12.4]
        assert body["speed"] == [3.2, 2.7]
        assert body["temperature"] == [21.6, 21.7]

    def test_max_points_averages_the_samples(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        body = sign_in(people.owner).client.get(_url(activity.id), params={"max_points": 2}).json()

        assert body["offsets_ms"] == [0, 1500]
        assert body["heart_rate"] == [100.0, 190.0]
        assert body["heart_rate_zones"] is not None

    @pytest.mark.parametrize("max_points", [0, 1, 10001, -3, "many"])
    def test_a_max_points_out_of_range_is_a_validation_error(self, sign_in, people, make_owned_activity, max_points):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id), params={"max_points": max_points})

        assert response.status_code == 422

    def test_an_activity_without_samples_is_a_200_with_an_empty_timeline(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity()

        response = sign_in(people.owner).client.get(_url(activity.id))

        assert response.status_code == 200
        assert response.json() == {"offsets_ms": [], "heart_rate_zones": None} | {name: None for name in _CHANNELS}

    def test_a_stranger_gets_the_404_a_missing_activity_gets(self, sign_in, people, make_owned_activity):
        shared = make_owned_activity(_VISIBILITY.PRIVATE, stage=_stage)
        client = sign_in(people.stranger).client

        refused = client.get(_url(shared.id))
        missing = client.get(_url(uuid.uuid4()))

        assert refused.status_code == missing.status_code == 404
        assert refused.json()["type"] == missing.json()["type"] == "urn:endurain:error:not-found"
        assert refused.json()["detail"] == missing.json()["detail"]

    def test_a_follower_gets_the_channels_a_followers_only_activity_does_not_hide(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_hr=True, hide_start_time=True)

        body = sign_in(people.follower).client.get(_url(activity.id)).json()

        assert body["offsets_ms"] == [0, 1000, 2000]
        assert body["heart_rate"] is None
        assert body["heart_rate_zones"] is None
        assert body["power"] == [250.5, 260.0, 270.0]

    def test_the_old_per_type_route_is_gone(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        assert sign_in(people.owner).client.get(f"{_url(activity.id)}/power").status_code == 404
