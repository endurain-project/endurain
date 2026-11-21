"""The stream routes, through the production application: what a viewer reads, per stream type."""

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


def _url(activity_id: uuid.UUID | str, stream_type: str = "") -> str:
    return f"{core_config.ROOT_PATH}/activities/{activity_id}/streams" + (f"/{stream_type}" if stream_type else "")


def _stage(db, activity):
    make_stream(db, activity, _HR, [{"time": _TIME, "hr": 100}, {"time": _TIME, "hr": 190}])
    make_stream(db, activity, _POWER, [{"time": _TIME, "power": 250.5}])


class TestList:
    def test_the_owner_gets_the_streams_in_a_page_envelope_with_the_hr_zones(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(stage=_stage, total_timer_time=100.0)

        response = sign_in(people.owner).client.get(_url(activity.id))

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 200, None)
        by_type = {item["stream_type"]: item for item in body["items"]}
        assert set(by_type) == {"heart_rate", "power"}
        assert by_type["heart_rate"]["zone_percentages"]["hr"]["zone_1"]["percent"] == 50.0
        assert by_type["power"]["zone_percentages"] is None
        assert by_type["power"]["stream_waypoints"] == [{"time": _TIME, "power": 250.5}]

    def test_a_page_holds_its_slice_and_names_the_next_one(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        first = sign_in(people.owner).client.get(_url(activity.id), params={"page_number": 1, "num_records": 1}).json()

        assert (len(first["items"]), first["total"], first["next"]) == (1, 2, 2)

    @pytest.mark.parametrize("params", [{"page_number": 0}, {"num_records": 0}, {"num_records": 201}])
    def test_a_paging_value_out_of_range_is_a_validation_error(self, sign_in, people, make_owned_activity, params):
        activity = make_owned_activity(stage=_stage)

        assert sign_in(people.owner).client.get(_url(activity.id), params=params).status_code == 422

    def test_a_stranger_gets_the_page_an_activity_that_does_not_exist_gets(self, sign_in, people, make_owned_activity):
        shared = make_owned_activity(_VISIBILITY.PRIVATE, stage=_stage)
        client = sign_in(people.stranger).client

        refused = client.get(_url(shared.id))
        missing = client.get(_url(uuid.uuid4()))

        assert refused.status_code == missing.status_code == 200
        assert (
            refused.json() == missing.json() == {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}
        )

    def test_a_follower_gets_the_streams_a_followers_only_activity_does_not_hide(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_hr=True, hide_start_time=True)

        body = sign_in(people.follower).client.get(_url(activity.id)).json()

        assert [item["stream_type"] for item in body["items"]] == ["power"]
        assert body["items"][0]["stream_waypoints"] == [{"power": 250.5}]
        assert body["total"] == 1


class TestOne:
    def test_the_owner_gets_one_stream_by_its_type_name(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id, "power"))

        assert response.status_code == 200
        body = response.json()
        assert (body["stream_type"], body["activity_id"]) == ("power", str(activity.id))

    def test_a_stream_the_activity_does_not_have_is_a_404_problem(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        response = sign_in(people.owner).client.get(_url(activity.id, "cadence"))

        assert response.status_code == 404
        assert response.json()["type"] == "urn:endurain:error:not-found"

    def test_a_hidden_stream_is_the_same_404_for_a_follower_and_a_stream_for_the_owner(
        self, sign_in, people, make_owned_activity
    ):
        activity = make_owned_activity(_VISIBILITY.FOLLOWERS, stage=_stage, hide_power=True)

        hidden = sign_in(people.follower).client.get(_url(activity.id, "power"))
        missing = sign_in(people.follower).client.get(_url(activity.id, "cadence"))

        assert hidden.status_code == missing.status_code == 404
        assert hidden.json()["detail"] == missing.json()["detail"]
        assert sign_in(people.owner).client.get(_url(activity.id, "power")).status_code == 200

    def test_a_type_that_is_not_a_stream_type_is_a_validation_error(self, sign_in, people, make_owned_activity):
        activity = make_owned_activity(stage=_stage)

        assert sign_in(people.owner).client.get(_url(activity.id, "3")).status_code == 422
        assert sign_in(people.owner).client.get(_url(activity.id, "altitude")).status_code == 422
